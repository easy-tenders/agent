#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Скидка победителя от плановой суммы.

    python winprice2.py [ключевое слово]

Читает РУССКУЮ часть протокола, колонки определяет по заголовку таблицы —
они различаются от протокола к протоколу.

Закупки из одного источника портал отдаёт HTML-ом вместо протокола об итогах:
там приглашённый поставщик и торга нет. Такие пропускаются и считаются
отдельной строкой — молча терять их нельзя, иначе непонятно, что осталось
за кадром.
"""
import re
import statistics
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common

TMP = common.cache_dir("wp")
KEY = sys.argv[1] if len(sys.argv) > 1 else "кондиционер"

txt = common.strip_tags
num = common.num


def parse_protocol(t):
    """-> (плановая сумма, [(имя, бин, общая сумма)], есть_ли_цена_за_единицу)"""
    i = t.find("Протокол об итогах")
    if i < 0:
        return None, [], False
    ru = t[i:]
    plan = None
    m = re.search(r"Запланированная сумма,?\s*" + common.TENGE + r"\s+([\d\s.,]+)", ru)
    if m:
        plan = num(m.group(1))
    has_unit = bool(re.search(r"Цена за\s*\n?\s*единицу", ru))
    # строки участников: № имя БИН <числа...> дата. Режем строку по двум и более
    # пробелам (колонки pdftotext -layout) — одно регулярное выражение на всю
    # строку зацикливалось на длинных протоколах (2026-10-22).
    rows = []
    for line in ru.splitlines():
        if not re.match(r"\s*\d{1,2}\s+\S", line):
            continue
        c = re.split(r"\s{2,}", line.strip())
        if len(c) < 4 or not re.match(common.PROTO_DATE, c[-1]):
            continue
        bi = next((i for i, x in enumerate(c) if re.fullmatch(r"\d{10,12}", x.strip())), None)
        if bi is None:
            continue
        name = common.participant_name(c, bi)
        vals = [num(x) for x in c[bi + 1:-1] if re.fullmatch(r"\d[\d .,]*", x.strip())]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        # общая сумма поставщика = последнее число перед датой
        rows.append((name, c[bi].strip(), vals[-1]))
    uniq = {}
    for n, b, tot in rows:
        uniq.setdefault(b, (n, b, tot))
    return plan, list(uniq.values()), has_unit


found = common.search_lots(KEY, common.DONE_STATUSES, TMP, max_pages=1)
if found is None:
    sys.exit("не удалось получить список состоявшихся закупок")
rows, _ = found
if not rows:
    sys.exit(f"по слову «{KEY}» состоявшихся закупок не найдено")

anns = []
for r in rows:
    a = re.search(r"/ru/announce/index/(\d+)", r)
    c = [txt(x) for x in re.findall(r"<td.*?</td>", r, re.S) if txt(x)]
    if a and c and a.group(1) not in [x[1] for x in anns]:
        anns.append((c[0].split()[0], a.group(1)))

res = []
skipped_single_source = 0
no_protocol = 0
for lot, ann in anns:
    if len(res) >= 15:
        break
    doc = TMP / f"pr_{ann}.bin"
    if not doc.exists():
        ph = TMP / f"p_{ann}.html"
        if not common.portal_fetch(f"/ru/announce/index/{ann}?tab=protocols", ph):
            continue
        h = ph.read_text(encoding="utf-8", errors="ignore")
        link = common.PROTOCOL_LINK.search(h)
        if not link:
            no_protocol += 1
            continue
        if not common.fetch(link.group(1), doc):
            continue
    text, fmt = common.document_text(doc)
    if fmt == "html":
        skipped_single_source += 1
        continue
    plan, parts, has_unit = parse_protocol(text)
    if not plan or not parts:
        continue
    totals = sorted(p[2] for p in parts)
    win = totals[0]
    if win > plan * 1.5 or win < plan * 0.05:
        continue   # явный промах парсера — выбрасываем
    # Второе место проверяем так же: в протоколах встречаются склеенные колонки,
    # и без этой отбраковки в отчёт уезжает «2-е место 585 202 924 800».
    second = totals[1] if len(totals) > 1 else None
    if second is not None and (second > plan * 1.5 or second < win):
        second = None
    res.append(dict(lot=lot, n=len(parts), plan=plan, win=win,
                    disc=round((plan - win) / plan * 100, 1), second=second))

print(f"{'лот':<20} {'уч.':>4} {'плановая':>12} {'победа':>12} {'скидка':>7} {'2-е место':>12}")
print("-" * 74)
for r in res:
    sec = f"{r['second']:,.0f}" if r['second'] else "—"
    print(f"{r['lot']:<20} {r['n']:>4} {r['plan']:>12,.0f} {r['win']:>12,.0f} "
          f"{r['disc']:>6}% {sec:>12}")

ds = [r["disc"] for r in res]
if ds:
    print(f"\nразобрано протоколов: {len(res)}")
    print(f"скидка победителя от плановой: медиана {statistics.median(ds):.1f}%, "
          f"мин {min(ds)}%, макс {max(ds)}%")
    print(f"участников: медиана {statistics.median([r['n'] for r in res]):.0f}, "
          f"макс {max(r['n'] for r in res)}")
    tight = [r for r in res if r["second"] and r["win"] > 0]
    if tight:
        gaps = [round((r["second"] - r["win"]) / r["win"] * 100, 1) for r in tight]
        print(f"отрыв победителя от второго места: медиана {statistics.median(gaps):.1f}%, "
              f"мин {min(gaps)}%")
if skipped_single_source:
    print(f"\nпропущено закупок из одного источника: {skipped_single_source} "
          f"— там приглашённый поставщик, торга нет")
if no_protocol:
    print(f"без протокола на портале: {no_protocol}")
