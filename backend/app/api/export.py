from __future__ import annotations

import markdown
import pdfkit

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


def convert_md_to_pdf(content: str) -> bytes:
    """Convert Markdown content to PDF bytes via HTML (pdfkit + wkhtmltopdf)."""
    html_body = markdown.markdown(
        content,
        extensions=["mdx_math"],
    )
    html = _HTML_TEMPLATE.format(body=html_body)
    pdf_bytes: bytes = pdfkit.from_string(
        html,
        False,
        options={"javascript-delay": "5000"},
    )
    return pdf_bytes
