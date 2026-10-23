#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Общее для всех скриптов движка: сеть, временные папки, чтение документов.

Работает на Windows, macOS и Linux. Внешних библиотек не требует; если для
чтения PDF в системе нет ни одного инструмента, скрипт останавливается с
внятным сообщением — что именно поставить.
"""
import html as _html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Единый User-Agent. Портал отдаёт публичную часть без ЭЦП и без cookie.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/120 Safari/537.36"

# Правило базы: между запросами к порталу — пауза. Держим её здесь, а не
# россыпью time.sleep по скриптам. 0.35 с портал не выдержал на выдаче в
# 300 лотов (2026-10-22: «429 Too Many Requests» на 46 карточках) — теперь 0.8 с,
# а на отказ — ожидание и повтор.
PAUSE = 0.8
BACKOFF = (15, 45, 90)   # секунды ожидания после «слишком много запросов»
_last_request = 0.0


def _blocked(body):
    """Портал отвечает страницей-отказом вместо данных — её нельзя класть в кэш."""
    head = body[:2000]
    return b"Too Many Requests" in head or b"<title>429" in head


def base_dir():
    """Корень базы — на два уровня выше этого файла (engine/common.py)."""
    return Path(__file__).resolve().parent.parent


def cache_dir(tag):
    """Папка под промежуточные файлы прогона. Не в базе: в базу попадает
    только то, что записано операцией."""
    d = Path(tempfile.gettempdir()) / "tender-agent" / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


def fetch(url, dest, min_size=0):
    """Скачать url в dest. Уже скачанное не трогаем — прогон можно продолжить
    с того места, где оборвался. Возвращает True, если файл на месте."""
    global _last_request
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > min_size:
        with dest.open("rb") as fh:
            if not _blocked(fh.read(2000)):
                return True
        dest.unlink()   # в кэше лежит страница-отказ портала, а не данные
    for attempt in range(len(BACKOFF) + 1):
        wait = PAUSE - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            body = b"<title>429" if e.code == 429 else None
            if body is None:
                print(f"  не скачалось: {url} — {e}", file=sys.stderr)
                _last_request = time.monotonic()
                return False
        except (urllib.error.URLError, OSError) as e:
            print(f"  не скачалось: {url} — {e}", file=sys.stderr)
            _last_request = time.monotonic()
            return False
        _last_request = time.monotonic()
        if not _blocked(body):
            dest.write_bytes(body)
            return dest.stat().st_size > min_size
        if attempt < len(BACKOFF):
            print(f"  портал просит притормозить — жду {BACKOFF[attempt]} с", file=sys.stderr)
            time.sleep(BACKOFF[attempt])
    print(f"  не скачалось: {url} — портал отказывает (429), повторите позже", file=sys.stderr)
    return False


def read(url):
    """Скачать и вернуть как текст, без файла на диске."""
    global _last_request
    wait = PAUSE - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        body = resp.read()
    _last_request = time.monotonic()
    return body.decode("utf-8", "ignore")


# ── портал госзакупок ────────────────────────────────────────────────────────
# С осени 2026 `goszakup.gov.kz` переадресует поиск, лоты и объявления на
# `old.goszakup.gov.kz` (корень — на новую `zakup.gov.kz`, поиска лотов там нет).
# `procurement.gov.kz` — зеркало того же портала. Проверено 2026-10-22. Адрес
# держим здесь одной строкой: переедет снова — правится одно место.
PORTAL = "https://old.goszakup.gov.kz"
PORTAL_MIRRORS = ("https://procurement.gov.kz",)

# Статусы лота в фильтре поиска портала:
#   210 — опубликован · 220 — приём заявок · 240 — приём ценовых предложений
#   (основная масса запросов ценовых предложений) · 360 — закупка состоялась.
OPEN_STATUSES = (210, 220, 240)
DONE_STATUSES = (360,)

# Путь карточки лота в выдаче — хост не важен, берём путь и строим адрес сами.
LOT_PATH = re.compile(r'href="https?://[\w.]*?(?:goszakup|procurement)\.gov\.kz'
                      r'(/ru/subpriceoffer/index/(\d+)/(\d+))"')
# Ссылка на файл протокола.
PROTOCOL_LINK = re.compile(r'href="(https?://[\w.]*goszakup\.gov\.kz/files/download_file/[^"]+)"')
# «тенге» в русском блоке протокола, «теңге» — в казахском.
TENGE = "те[нң]ге"
# Дата подачи в строке участника протокола: раньше 2026-10-15, с осени 2026 —
# 15.10.2026 (время рядом). Принимаем обе.
PROTO_DATE = r"(?:20\d\d-\d\d-\d\d|\d\d\.\d\d\.20\d\d)"


def participant_name(cells, bin_index):
    """Имя участника из строки протокола, разрезанной по колонкам: всё до БИН,
    без номера строки (он бывает и отдельной колонкой, и в начале имени)."""
    parts = [re.sub(r"^\d{1,2}\s+", "", x.strip()) for x in cells[:bin_index]]
    return " ".join(x for x in parts if x and not re.fullmatch(r"\d{1,2}", x))


def portal_fetch(path, dest, min_size=0):
    """Скачать страницу портала по пути (`/ru/...`): основной адрес, при отказе —
    зеркало. True, если файл на месте."""
    for host in (PORTAL,) + PORTAL_MIRRORS:
        if fetch(host + path, dest, min_size=min_size):
            return True
    return False


def run_tag(*parts):
    """Короткая метка для имён файлов кэша: своё слово — свой файл, чтобы второй
    прогон с другим словом не взял выдачу первого."""
    import hashlib
    return hashlib.md5("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:10]


def search_lots(key, statuses, tmp, max_pages=20):
    """Строки (`<tr>…</tr>`) выдачи поиска лотов по слову и статусам — со всех
    страниц, по 50 на страницу. -> (строки, всего записей по счётчику портала).
    None — если первая страница не скачалась."""
    import urllib.parse
    tag = run_tag(key, *statuses)
    rows, total = [], None
    for page in range(1, max_pages + 1):
        q = ("filter%5Bname%5D=" + urllib.parse.quote(key)
             + "".join(f"&filter%5Bstatus%5D%5B%5D={s}" for s in statuses)
             + f"&count_record=50&page={page}")
        dest = Path(tmp) / f"list_{tag}_p{page}.html"
        if not portal_fetch("/ru/search/lots?" + q, dest, min_size=500):
            if page == 1:
                return None
            break
        d = dest.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'<table[^>]*id="search-result".*?</table>', d, re.S)
        if not m:
            tables = re.findall(r"<table.*?</table>", d, re.S)
            if len(tables) < 2:
                break
            m = re.match(r".*", tables[1], re.S)
        body = re.search(r"<tbody.*?</tbody>", m.group(0), re.S)
        got = re.findall(r"<tr.*?</tr>", body.group(0), re.S) if body else []
        rows += got
        c = re.search(r"Показано c \d+ по \d+ из ([\d\s]+) записей", strip_tags(d))
        if c:
            total = int(re.sub(r"\D", "", c.group(1)))
        if len(got) < 50 or (total is not None and len(rows) >= total):
            break
    return rows, total


def parse_date(s):
    """Дата портала '2026-10-22 12:06:04' -> datetime или None."""
    import datetime
    m = re.search(r"(20\d\d-\d\d-\d\d)(?:\s+(\d\d:\d\d(?::\d\d)?))?", s or "")
    if not m:
        return None
    fmt = "%Y-%m-%d %H:%M:%S" if m.group(2) and m.group(2).count(":") == 2 else \
          "%Y-%m-%d %H:%M" if m.group(2) else "%Y-%m-%d"
    return datetime.datetime.strptime(" ".join(x for x in m.groups() if x), fmt)


# ── чтение документов ────────────────────────────────────────────────────────
# Портал отдаёт протоколы двумя разными форматами:
#   PDF   — протокол об итогах (ЗЦП, аукцион, конкурс);
#   HTML  — закупка из одного источника (ИОИ), другой род документа.
# Расширение файла об этом не говорит — смотрим на содержимое.

MISSING_PDF_TOOL = """
Не могу прочитать PDF: в системе нет ни pdftotext, ни библиотеки pypdf.
Поставь любое из двух:
  pip install pypdf                     — проще, ставится куда угодно
  poppler (даёт pdftotext)              — Windows: winget install poppler
                                          macOS:   brew install poppler
"""


def kind_of(path):
    """'pdf' | 'html' | 'unknown' — по сигнатуре файла, не по имени."""
    head = Path(path).open("rb").read(512).lstrip()
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:1] == b"<":
        return "html"
    return "unknown"


def _pdftotext_binary():
    """pdftotext, если он есть в PATH. Абсолютных путей не зашиваем —
    на каждой машине он лежит по-своему."""
    return shutil.which("pdftotext")


def pdf_text(path):
    """Текст из PDF с сохранением колоночной раскладки — парсеры протоколов
    разбирают строки по двум и более пробелам, раскладка им нужна."""
    exe = _pdftotext_binary()
    if exe:
        out = Path(str(path) + ".txt")
        subprocess.run([exe, "-layout", str(path), str(out)], capture_output=True)
        if out.exists():
            return out.read_text(encoding="utf-8", errors="ignore")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(MISSING_PDF_TOOL.strip())
    reader = PdfReader(str(path))
    return "\n".join(p.extract_text(extraction_mode="layout") or ""
                     for p in reader.pages)


def _cell(s):
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def html_text(source):
    """HTML-документ в колоночный текст: ячейки таблицы разделены двумя
    пробелами — тот же вид, что даёт `pdftotext -layout`, поэтому парсеры
    протоколов работают с обоими форматами одинаково."""
    if not isinstance(source, str) or "<" not in source:
        source = Path(source).read_text(encoding="utf-8", errors="ignore")
    lines = []
    for table in re.findall(r"<table.*?</table>", source, re.S):
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            cells = [_cell(c) for c in re.findall(r"<t[dh].*?</t[dh]>", row, re.S)]
            if any(cells):
                lines.append("  ".join(cells))
        lines.append("")
    return "\n".join(lines)


def document_text(path):
    """(текст, формат) для любого скачанного документа.

    Формат возвращается наружу нарочно: закупка из одного источника приходит
    HTML-ом, и её надо пропускать осознанно и со счётом, а не молча — иначе
    статистика тихо недосчитывает лоты и никто об этом не знает.
    """
    k = kind_of(path)
    if k == "pdf":
        return pdf_text(path), "pdf"
    if k == "html":
        return html_text(path), "html"
    return "", "unknown"


# ── мелочи, общие для парсеров ───────────────────────────────────────────────

def strip_tags(s):
    return _cell(s)


def num(s):
    """Число из строки портала: '1 234 567,89' -> 1234567.89. None, если не число."""
    s = re.sub(r"[^\d.,]", "", str(s)).replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def add_engine_to_path():
    """Чтобы `import common` работал из scripts/ и report/ при любом cwd."""
    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)
