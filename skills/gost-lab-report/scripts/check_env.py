"""Быстрая проверка окружения для gost-lab-report.

Использование: python check_env.py
Выход: 0 — слой 0 (сборка docx) готов; 1 — сборка невозможна.

Слои зависимостей:
  слой 0 (обязательный): pandoc, python-docx, docxcompose — сборка документа
  слой 1 (опциональный): LibreOffice + python-uno — авто-СОДЕРЖАНИЕ и {{PAGES}};
      без него содержание обновляется в Word (Ctrl+A, F9)
"""

import shutil
import subprocess
import sys


def find_soffice():
    path = shutil.which("soffice")
    if path:
        return path
    candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for c in candidates:
        if shutil.which(c):
            return c
    return None


def main():
    core_ok = True
    print("=== Слой 0: сборка docx (обязательный) ===")

    pandoc = shutil.which("pandoc")
    if pandoc:
        ver = subprocess.run([pandoc, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout.splitlines()[0]
        print(f"[OK]   {ver}")
    else:
        core_ok = False
        print("[FAIL] pandoc не найден — установите: apt/brew/choco install pandoc")

    for pkg, module in (("python-docx", "docx"), ("docxcompose", "docxcompose")):
        try:
            __import__(module)
            from importlib.metadata import version
            print(f"[OK]   {pkg} {version(pkg)}")
        except ImportError:
            core_ok = False
            print(f"[FAIL] {pkg} не найден — pip install {pkg} "
                  "(на Ubuntu 23+ добавьте --break-system-packages)")

    print("\n=== Слой 1: авто-СОДЕРЖАНИЕ и {{PAGES}} (опциональный) ===")
    soffice = find_soffice()
    if soffice:
        print(f"[OK]   LibreOffice: {soffice}")
        try:
            import uno  # noqa: F401
            print("[OK]   python-uno доступен — авто-обновление полей работает")
        except ImportError:
            print("[WARN] python-uno недоступен этому питону — авто-обновление полей не сработает; "
                  "на Debian/Ubuntu: apt install python3-uno и системный python3; "
                  "на Windows/macOS — обновите содержание в Word (Ctrl+A, F9)")
    else:
        print("[WARN] LibreOffice не найден — сборка работает, но СОДЕРЖАНИЕ обновится "
              "только в Word (Ctrl+A, F9), а {{PAGES}} останется плейсхолдером. "
              "Ставить LibreOffice (~700 МБ) стоит только ради этой функции — спросите пользователя.")

    print()
    if core_ok:
        print("Итог: сборка документов доступна.")
        return 0
    print("Итог: слой 0 неполон — сборка не запустится, установите недостающее.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
