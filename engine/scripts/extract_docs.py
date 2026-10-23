#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Вытащить текст из docx/xlsx/pdf/xls в подпапку `_text/`.

    python extract_docs.py <папка с материалами> [ещё папка ...]

Папка указывается явно — скрипт разбирает материалы владельца, и где они лежат,
знает только тот, кто запускает. Обходит указанные папки рекурсивно.

docx и xlsx читаются напрямую (это zip с xml) — ничего ставить не надо.
Для pdf нужен pdftotext или pypdf, для старого .xls — LibreOffice или пересохранить
в xlsx; при их отсутствии файл пропускается со строкой в отчёте, остальные читаются.
"""
import html
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common

if len(sys.argv) < 2:
    sys.exit("нужна папка с материалами: python extract_docs.py <папка> [ещё папка ...]")
SOURCES = [Path(a).expanduser().resolve() for a in sys.argv[1:]]
for s in SOURCES:
    if not s.is_dir():
        sys.exit(f"это не папка: {s}")


def strip_xml(x):
    x = re.sub(r"</w:p>|</a:p>|</w:tr>", "\n", x)
    x = re.sub(r"</w:tc>", "\t", x)
    return html.unescape(re.sub(r"<[^>]+>", "", x))


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        parts = [n for n in z.namelist() if n.startswith("word/") and n.endswith(".xml")
                 and ("document" in n or "header" in n or "footer" in n)]
        return "\n".join(strip_xml(z.read(n).decode("utf-8", "ignore")) for n in sorted(parts))


def xlsx_text(p):
    with zipfile.ZipFile(p) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            raw = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
            shared = [html.unescape(re.sub(r"<[^>]+>", "", si))
                      for si in re.findall(r"<si>(.*?)</si>", raw, re.S)]
        out = []
        for n in sorted(x for x in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", x)):
            raw = z.read(n).decode("utf-8", "ignore")
            out.append(f"--- {n} ---")
            for row in re.findall(r"<row[^>]*>(.*?)</row>", raw, re.S):
                cells = []
                for attrs, body in re.findall(r"<c\b([^>]*)>(.*?)</c>", row, re.S):
                    f = re.search(r"<f[^>]*>(.*?)</f>", body, re.S)
                    v = re.search(r"<v>(.*?)</v>", body, re.S)
                    t = re.search(r'\bt="([^"]+)"', attrs)
                    val = ""
                    if v:
                        val = v.group(1)
                        if t and t.group(1) == "s" and val.isdigit() and int(val) < len(shared):
                            val = shared[int(val)]
                    if f:
                        val = f"{val} [={html.unescape(re.sub('<[^>]+>', '', f.group(1)))}]"
                    if val.strip():
                        cells.append(val.strip())
                if cells:
                    out.append(" | ".join(cells))
        return "\n".join(out)


def xls_text(p):
    """Старый бинарный .xls. Стандартной библиотекой не читается — пробуем тем,
    что есть в системе; если нечем, честно говорим, что делать."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        out = p.parent / "_conv"
        out.mkdir(exist_ok=True)
        subprocess.run([soffice, "--headless", "--convert-to", "xlsx", "--outdir",
                        str(out), str(p)], capture_output=True, timeout=180)
        conv = out / (p.stem + ".xlsx")
        if conv.exists():
            return xlsx_text(conv)
    textutil = shutil.which("textutil")          # есть только в macOS
    if textutil:
        r = subprocess.run([textutil, "-convert", "txt", "-stdout", str(p)],
                           capture_output=True, text=True, timeout=90)
        if r.stdout.strip():
            return r.stdout
    return ("(старый формат .xls не прочитан — пересохрани файл как .xlsx "
            "или поставь LibreOffice)")


def extract(p):
    ext = p.suffix.lower().lstrip(".")
    try:
        if ext == "docx":
            return docx_text(p)
        if ext == "xlsx":
            return xlsx_text(p)
        if ext == "pdf":
            return common.pdf_text(p)
        if ext == "xls":
            return xls_text(p)
    except RuntimeError as e:                    # нечем читать PDF — сообщение из common
        return f"(не прочитан: {e})"
    except Exception as e:
        return f"(ошибка: {e})"
    return ""


KNOWN = {"docx", "xlsx", "pdf", "xls"}
report = []
for src in SOURCES:
    out_dir = src / "_text"
    out_dir.mkdir(exist_ok=True)
    for p in sorted(src.rglob("*")):
        if not p.is_file() or "_text" in p.parts or "_conv" in p.parts:
            continue
        if p.suffix.lower().lstrip(".") not in KNOWN:
            continue
        text = re.sub(r"\n{3,}", "\n\n", extract(p) or "").strip()
        rel = p.relative_to(src)
        dst = out_dir / (str(rel).replace("/", "__").replace("\\", "__") + ".txt")
        dst.write_text(text, encoding="utf-8")
        report.append(f"{len(text):>7}  {rel}")
    print(f"— {src} → {out_dir}")

print("\n".join(report) if report else "подходящих файлов (docx/xlsx/pdf/xls) не найдено")
