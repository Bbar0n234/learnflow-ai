from __future__ import annotations

import subprocess

import markdown
import structlog
from pdfkit import PDFKit

from app.services.exceptions import UpstreamUnavailableError

logger = structlog.get_logger()

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script type="text/javascript" async
  src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.9/MathJax.js?config=TeX-AMS-MML_HTMLorMML">
</script>
<style>
body {{ font-family: sans-serif; margin: 2em; line-height: 1.6; }}
pre {{ background: #f4f4f4; padding: 1em; overflow-x: auto; }}
code {{ background: #f4f4f4; padding: 0.2em 0.4em; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def convert_md_to_pdf(content: str, timeout: int = 30) -> bytes:
    """Convert Markdown content to PDF bytes via HTML (pdfkit + wkhtmltopdf).

    ``pdfkit`` exposes no timeout of its own — ``pdfkit.from_string`` runs the
    ``wkhtmltopdf`` subprocess via ``Popen.communicate()`` with no deadline, so a
    hung render would pin an ``anyio.to_thread`` worker forever. We instead build
    the command through pdfkit (keeping its option handling) and run it via
    ``subprocess.run(timeout=...)``, which kills the process tree on expiry.

    Raises:
        UpstreamUnavailableError (504): wkhtmltopdf exceeded ``timeout`` seconds.
        UpstreamUnavailableError (502): wkhtmltopdf failed or is unavailable.
    """
    html_body = markdown.markdown(
        content,
        extensions=["mdx_math"],
    )
    html = _HTML_TEMPLATE.format(body=html_body)

    job = PDFKit(html, "string", options={"javascript-delay": "5000"})
    args = job.command()
    stdin = job.source.to_s().encode("utf-8")

    try:
        result = subprocess.run(
            args,
            input=stdin,
            capture_output=True,
            env=job.environ,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        logger.error("pdf render timed out", timeout=timeout, exc_info=True)
        raise UpstreamUnavailableError(
            code="pdf-render-timeout",
            status=504,
            detail="PDF rendering timed out",
        ) from e
    except OSError as e:
        # wkhtmltopdf binary missing / not executable, etc.
        logger.error("pdf render failed to start", exc_info=True)
        raise UpstreamUnavailableError(
            code="pdf-render-failed",
            status=502,
            detail="PDF rendering failed",
        ) from e

    # wkhtmltopdf can exit non-zero yet still emit a valid PDF (resource
    # warnings). Reuse pdfkit's own heuristic: handle_error returns on success
    # and raises IOError (== OSError) on a genuine failure.
    stderr = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace")
    try:
        job.handle_error(result.returncode, stderr)
    except OSError as e:
        logger.error("pdf render failed", returncode=result.returncode, exc_info=True)
        raise UpstreamUnavailableError(
            code="pdf-render-failed",
            status=502,
            detail="PDF rendering failed",
        ) from e

    return result.stdout
