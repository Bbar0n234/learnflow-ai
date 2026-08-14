#!/bin/bash
# Smoke test: pandoc markdown -> docx conversion, verified two ways —
# the output is a genuine ZIP container (docx's actual format, checked via
# its local-file-header magic bytes) and python-docx can read the result
# back and find the source content.
set -euo pipefail

NAME="pandoc_docx"

fail() {
    echo "FAIL ${NAME}: $1" >&2
    exit 1
}

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

md_file="${tmpdir}/smoke.md"
docx_file="${tmpdir}/smoke.docx"

cat >"${md_file}" <<'EOF'
# Smoke heading

Smoke paragraph via pandoc.
EOF

pandoc "${md_file}" -o "${docx_file}" || fail "pandoc conversion failed"

[ -s "${docx_file}" ] || fail "docx output is empty"

# .docx is a ZIP container — verify the ZIP local-file-header magic bytes
# (PK\x03\x04) rather than trusting the file extension.
magic="$(head -c 4 "${docx_file}" | od -An -tx1 | tr -d ' \n')"
[ "${magic}" = "504b0304" ] || fail "unexpected magic bytes: ${magic}"

python3 - "${docx_file}" <<'PYEOF' || fail "python-docx readback failed"
import sys

from docx import Document

doc = Document(sys.argv[1])
text = "\n".join(p.text for p in doc.paragraphs)
assert "Smoke heading" in text, text
assert "Smoke paragraph via pandoc." in text, text
PYEOF

echo "PASS ${NAME}"
