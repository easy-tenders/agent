#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собрать все открытые лоты по ключевому слову с деталями.

    python collect_open.py [ключевое слово]

Открытые — статусы 210, 220, 240 (опубликован · приём заявок · приём ценовых
предложений), все страницы выдачи. Лоты с прошедшим сроком приёма отсеиваются и
считаются строкой. Результат — `lots.json` во временной папке прогона; путь
печатается в конце. Его читает rating.py.
"""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common

TMP = common.cache_dir("open")
KEY = sys.argv[1] if len(sys.argv) > 1 else "кондиционер"

txt = common.strip_tags
num = common.num

found = common.search_lots(KEY, common.OPEN_STATUSES, TMP)
if found is None:
    sys.exit("не удалось получить список лотов с портала")
rows, total = found
if not rows:
    sys.exit(f"по слову «{KEY}» открытых лотов не найдено")

lots, seen = [], set()
for r in rows:
    link = common.LOT_PATH.search(r)
    cells = [txt(c) for c in re.findall(r"<td.*?</td>", r, re.S) if txt(c)]
    if not link or not cells or link.group(3) in seen:
        continue
    seen.add(link.group(3))
    lots.append(dict(path=link.group(1), ann=link.group(2), lot_id=link.group(3),
                     num=cells[0].split()[0], method=cells[-2] if len(cells) > 5 else ""))

print(f"открытых лотов в выдаче: {len(lots)}"
      + (f" (портал насчитал {total})" if total is not None else ""), file=sys.stderr)
now = datetime.datetime.now()
out, expired, missed = [], 0, []
for l in lots:
    p = TMP / f"lot_{l['lot_id']}.html"
    if not common.portal_fetch(l["path"], p):
        missed.append(l["num"])
        continue
    h = p.read_text(encoding="utf-8", errors="ignore")
    tb = re.findall(r"<table.*?</table>", h, re.S)
    if not tb:
        missed.append(l["num"])
        continue
    ths = [txt(x) for x in re.findall(r"<th.*?</th>", tb[0], re.S)]
    tds = [txt(x) for x in re.findall(r"<td.*?</td>", tb[0], re.S)]
    f = dict(zip(ths, tds))
    deadline = f.get("Дата окончания приема заявок", "")
    end = common.parse_date(deadline)
    if end and end < now:
        expired += 1
        continue
    out.append(dict(
        lot=f.get("Лот №", l["num"]).replace(" История", "").strip(),
        ann=l["ann"],
        url=common.PORTAL + l["path"],
        status=f.get("Статус лота", ""),
        deadline=deadline,
        customer=f.get("Наименование заказчика", "")[:70],
        tru_code=f.get("Код ТРУ", ""),
        tru_name=f.get("Наименование ТРУ", ""),
        char=f.get("Краткая характеристика", ""),
        char2=f.get("Дополнительная характеристика", "")[:80],
        unit_price=num(f.get("Цена за единицу", "")),
        qty=num(f.get("Количество", "")),
        total=num(f.get("Запланированная сумма", "")),
        delivery=f.get("Срок поставки ТРУ", "")[:60],
        method=l["method"],
    ))

dst = TMP / f"lots_{common.run_tag(KEY)}.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
(TMP / "lots.json").write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
print(f"собрано карточек: {len(out)}; срок приёма уже прошёл — отсеяно: {expired}",
      file=sys.stderr)
if missed:
    print(f"НЕ СКАЧАЛИСЬ карточки: {len(missed)} — {', '.join(missed[:10])}"
          + (" …" if len(missed) > 10 else "")
          + ". Запустите тот же поиск ещё раз позже: уже скачанное не перекачивается,"
          " возьмутся только эти. Не скачалась и со второго раза — портал отдаёт"
          " её пустой: открыть карточку в браузере.", file=sys.stderr)
for r in out:
    print(f"{r['lot']:<20} {str(r['qty'] or ''):>4} × {r['unit_price'] or 0:>10,.0f} "
          f"= {r['total'] or 0:>11,.0f} | до {r['deadline'][:16]} | {r['char'][:44]}")
print(f"\nданные лотов: {dst} (копия — lots.json рядом)", file=sys.stderr)
