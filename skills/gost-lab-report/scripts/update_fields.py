#!/usr/bin/env python3
"""Update Word fields (TOC page numbers etc.) in a .docx in place.

Spawns headless LibreOffice with a UNO socket, loads the document, refreshes
all document indexes and text fields, stores the file back in docx format.

Usage:
    python update_fields.py <file.docx>

Requires libreoffice + pyuno. Exits non-zero on failure so the caller can
fall back to the «обновите поле по F9» placeholder behaviour.
"""

import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

PORT = 21734  # фиксированный необычный порт, чтобы не толкаться с юзерским LO

# Старые LibreOffice (7.4, Debian 12) при round-trip'е переименовывают styleId
# в свои нативные — контракт стилей сборки ломается (verify.py, постпроцессинг).
# После сохранения возвращаем канонические id. LO >= 24.2 ничего не переименовывает.
CANONICAL_STYLE_IDS = {
    "TextBody": "BodyText",
    "Contents1": "TOC1",
    "Contents2": "TOC2",
}


def restore_canonical_style_ids(path):
    with zipfile.ZipFile(path) as zf:
        entries = {info.filename: zf.read(info.filename) for info in zf.infolist()}
    styles = entries.get("word/styles.xml", b"").decode("utf-8")
    renames = {
        alias: canon
        for alias, canon in CANONICAL_STYLE_IDS.items()
        if f'w:styleId="{alias}"' in styles
        and f'w:styleId="{canon}"' not in styles  # не плодить дубли id
    }
    if not renames:
        return
    for name in list(entries):
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        xml = entries[name].decode("utf-8")
        for alias, canon in renames.items():
            xml = xml.replace(f'w:styleId="{alias}"', f'w:styleId="{canon}"')
            xml = xml.replace(f'w:val="{alias}"', f'w:val="{canon}"')
        entries[name] = xml.encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    print(f"Canonical styleIds restored: {', '.join(sorted(renames))}")


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python update_fields.py <file.docx> [path-to-soffice]")
        return 1
    path = Path(sys.argv[1]).resolve()
    if not path.exists():
        print(f"File not found: {path}")
        return 1
    soffice = sys.argv[2] if len(sys.argv) == 3 else "soffice"

    import uno  # noqa: F401  (fail fast, до запуска soffice)
    from com.sun.star.beans import PropertyValue

    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [
                soffice,
                "--headless",
                "--invisible",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation={Path(profile).as_uri()}",
                f"--accept=socket,host=127.0.0.1,port={PORT};urp;",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            ctx = _connect(PORT)
            smgr = ctx.ServiceManager
            desktop = smgr.createInstanceWithContext(
                "com.sun.star.frame.Desktop", ctx
            )

            hidden = PropertyValue()
            hidden.Name = "Hidden"
            hidden.Value = True
            doc = desktop.loadComponentFromURL(
                path.as_uri(), "_blank", 0, (hidden,)
            )
            try:
                doc.refresh()
                # {{PAGES}} — фактическое число страниц (после пагинации)
                search = doc.createSearchDescriptor()
                search.SearchString = "{{PAGES}}"
                if doc.findFirst(search):
                    pages = doc.getCurrentController().PageCount
                    replace = doc.createReplaceDescriptor()
                    replace.SearchString = "{{PAGES}}"
                    replace.ReplaceString = str(pages)
                    doc.replaceAll(replace)
                    doc.refresh()
                indexes = doc.getDocumentIndexes()
                for i in range(indexes.getCount()):
                    indexes.getByIndex(i).update()
                doc.getTextFields().refresh()

                fmt = PropertyValue()
                fmt.Name = "FilterName"
                fmt.Value = "MS Word 2007 XML"  # docx
                doc.storeToURL(path.as_uri(), (fmt,))
            finally:
                doc.close(False)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    restore_canonical_style_ids(path)
    print(f"Fields updated: {path}")
    return 0


def _connect(port, attempts=30, delay=0.5):
    import uno

    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )
    url = (
        f"uno:socket,host=127.0.0.1,port={port};urp;"
        "StarOffice.ComponentContext"
    )
    for _ in range(attempts):
        try:
            return resolver.resolve(url)
        except Exception:
            time.sleep(delay)
    raise RuntimeError("Cannot connect to headless LibreOffice")


if __name__ == "__main__":
    sys.exit(main())
