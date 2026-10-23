#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рейтинг открытых лотов по ожидаемой марже. Формулы — из файлов владельца.

    python rating.py <файл цен>

Файл цен обязателен и указывается явно. Это снимок рынка на конкретный день по
конкретной нише (`engine/data/ceny-rynka-*.json`) — считать новую нишу по
ценам старого прогона нельзя, поэтому значения по умолчанию здесь нет.

Читает лоты, собранные `collect_open.py`; результат кладёт рядом с ними.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common

if len(sys.argv) < 2:
    data = common.base_dir() / "engine" / "data"
    have = sorted(p.name for p in data.glob("ceny-rynka-*.json")) if data.exists() else []
    sys.exit("нужен файл цен: python rating.py <файл>\n"
             "есть в engine/data/: " + (", ".join(have) if have else "ни одного"))

prices_path = Path(sys.argv[1])
if not prices_path.exists():
    prices_path = common.base_dir() / "engine" / "data" / sys.argv[1]
if not prices_path.exists():
    sys.exit(f"файла цен нет: {sys.argv[1]}")

PRICES = json.loads(prices_path.read_text(encoding="utf-8"))
MARKET = [(p["признак"], p["цена"], p["модель"]) for p in PRICES["позиции"]]

TMP = common.cache_dir("open")
lots_path = TMP / "lots.json"
if not lots_path.exists():
    sys.exit(f"нет данных о лотах ({lots_path}) — сначала запусти collect_open.py")
lots = json.loads(lots_path.read_text(encoding="utf-8"))

print(f"цены: {PRICES.get('ниша', '?')}, сняты {PRICES.get('снято', '?')} "
      f"({prices_path.name})")


def market_price(char):
    for pat, price, name in MARKET:
        if re.search(pat, char, re.I):
            return price, name
    return None, "не определено"


rows = []
for l in lots:
    char = (l.get("char") or "") + " " + (l.get("char2") or "")
    unit, model = market_price(char)
    plan = l.get("total") or 0
    qty = l.get("qty") or 0
    method = l.get("method") or ""
    # цена подачи: ЗЦП/аукцион — по медиане ниши (-10%), из одного источника — по плановой
    is_zcp = "ценовых" in method.lower() or "укцион" in method.lower()
    bid = plan * 0.90 if is_zcp else plan
    cost = unit * qty if unit and qty else None
    base = dict(lot=l["lot"], plan=plan, bid=bid, model=model, method=method,
                char=char.strip()[:46], qty=qty, deadline=l.get("deadline", "")[:10])
    if cost is None:
        rows.append(dict(base, cost=None, m1=None, m2=None, pct=None))
        continue
    # упрощённый режим: налог 3% с оборота
    m1 = bid - cost - bid * 0.03
    # общеустановленный: КПН 20% с прибыли
    profit = bid - cost
    m2 = profit * 0.8 if profit > 0 else profit
    rows.append(dict(base, cost=cost, m1=m1, m2=m2, pct=(m1 / bid * 100) if bid else None))

ok = [r for r in rows if r["m1"] is not None]
ok.sort(key=lambda r: -r["m1"])

print(f"\n{'лот':<18} {'кол':>3} {'плановая':>10} {'подача':>10} {'закупка':>10} "
      f"{'марж.упр':>10} {'%':>6} {'марж.КПН':>10}")
print("-" * 92)
for r in ok:
    print(f"{r['lot']:<18} {r['qty']:>3.0f} {r['plan']:>10,.0f} {r['bid']:>10,.0f} "
          f"{r['cost']:>10,.0f} {r['m1']:>10,.0f} {r['pct']:>5.1f}% {r['m2']:>10,.0f}")

nod = [r for r in rows if r["m1"] is None]
print(f"\nне посчитано (нет рыночной цены): {len(nod)}")
for r in nod:
    print(f"   {r['lot']:<18} {r['char']}")

good = [r for r in ok if r["m1"] > 0]
print(f"\nвсего лотов: {len(rows)} | посчитано: {len(ok)} | прибыльных: {len(good)} "
      f"| убыточных: {len(ok) - len(good)}")
if good:
    print(f"суммарная маржа по прибыльным (упрощёнка): {sum(r['m1'] for r in good):,.0f} тенге")

dst = TMP / "rating.json"
dst.write_text(json.dumps(dict(prices=prices_path.name, snapshot=PRICES.get("снято"),
                               rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nрейтинг: {dst}", file=sys.stderr)
