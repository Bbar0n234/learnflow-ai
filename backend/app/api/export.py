from __future__ import annotations

import markdown
import pdfkit

from app.services.exceptions import UpstreamUnavailableError

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

    Raises:
        UpstreamUnavailableError (502): wkhtmltopdf failed or is unavailable.
    """
    html_body = markdown.markdown(
        content,
        extensions=["mdx_math"],
    )
    html = _HTML_TEMPLATE.format(body=html_body)
    try:
        pdf_bytes: bytes = pdfkit.from_string(
            html,
            False,
            options={"javascript-delay": "5000"},
        )
    except Exception as e:
        raise UpstreamUnavailableError(
            code="pdf-render-failed",
            status=502,
            detail="PDF rendering failed",
        ) from e
    return pdf_bytes
