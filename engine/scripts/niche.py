#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Статистика прошлых закупок по конкретному товару: участники, скидки, победители.

    python niche.py "ключевое слово" [метка]

Метка — имя папки прогона, чтобы разные товары не перетирали друг друга.
Без неё берётся первое слово запроса.

Закупки из одного источника (портал отдаёт их HTML-ом) считаются отдельно и в
статистику не идут: там приглашённый поставщик и торга нет.
"""
import collections
import json
import re
import statistics
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common

if len(sys.argv) < 2:
    sys.exit('нужно ключевое слово: python niche.py "кондиционер" [метка]')
KEY = sys.argv[1]
TAG = sys.argv[2] if len(sys.argv) > 2 else re.sub(r"\W+", "_", KEY.split()[0].lower())
T = common.cache_dir(f"niche_{TAG}")

txt = common.strip_tags


def num(s):
    """Строгий разбор ячейки протокола: колонок много, мусор отсеиваем."""
    s = s.strip()
    if not re.fullmatch(r"\d[\d ]*([.,]\d+)?", s):
        return None
    return float(s.replace(" ", "").replace(",", "."))


found = common.search_lots(KEY, common.DONE_STATUSES, T, max_pages=1)
if found is None:
    sys.exit("не удалось получить список состоявшихся закупок")
rows, total_found = found
if not rows:
    print(json.dumps({"key": KEY, "total": 0}, ensure_ascii=False))
    sys.exit()
anns = []
for r in rows:
    a = re.search(r"/ru/announce/index/(\d+)", r)
    if a and a.group(1) not in anns:
        anns.append(a.group(1))

res = []
skipped_single_source = 0
for ann in anns[:26]:
    doc = T / f"pr_{ann}.bin"
    if not doc.exists():
        ph = T / f"p_{ann}.html"
        if not common.portal_fetch(f"/ru/announce/index/{ann}?tab=protocols", ph):
            continue
        h = ph.read_text(encoding="utf-8", errors="ignore")
        link = common.PROTOCOL_LINK.search(h)
        if not link:
            continue
        if not common.fetch(link.group(1), doc):
            continue
    t, fmt = common.document_text(doc)
    if fmt == "html":
        skipped_single_source += 1
        continue
    i = t.find("Протокол об итогах")
    if i < 0:
        continue
    for seg in re.split(r"(?=Лот №)", t[i:])[1:]:
        lot = re.match(r"Лот №\s+(\S+)", seg)
        nm = re.search(r"Наименование лота\s+(.+)", seg)
        pm = re.search(r"Запланированная сумма,?\s*" + common.TENGE + r"\s+([\d\s.,]+?)\n", seg)
        if not (lot and pm):
            continue
        plan = num(pm.group(1))
        if not plan:
            continue
        parts = {}
        for line in seg.splitlines():
            if not re.match(r"\s*\d{1,2}\s+\S", line):
                continue
            c = re.split(r"\s{2,}", line.strip())
            if len(c) < 4 or not re.match(common.PROTO_DATE, c[-1]):
                continue
            bi = next((i for i, x in enumerate(c) if re.fullmatch(r"\d{10,12}", x.strip())), None)
            if bi is None:
                continue
            b = c[bi].strip()
            nums = [num(x) for x in c[bi + 1:-1]]
            nums = [x for x in nums if x and x > 1000]
            if nums:
                parts.setdefault(b, (common.participant_name(c, bi), nums[-1]))
        if not parts:
            continue
        arr = sorted(parts.values(), key=lambda v: v[1])
        win = arr[0]
        if not (plan * 0.3 <= win[1] <= plan * 1.05):
            continue
        res.append(dict(lot=lot.group(1), name=(nm.group(1).strip()[:46] if nm else ""),
                        plan=plan, win=win[1], winner=win[0][:28], n=len(arr),
                        disc=round((plan - win[1]) / plan * 100, 1)))

seen = set()
res = [r for r in res if not (r["lot"] in seen or seen.add(r["lot"]))]
out = dict(key=KEY, total=(total_found if total_found is not None else "?"), parsed=len(res),
           skipped_single_source=skipped_single_source, lots=res)
if res:
    ds = [r["disc"] for r in res]
    ns = [r["n"] for r in res]
    out.update(disc_med=statistics.median(ds), disc_avg=round(statistics.mean(ds), 1),
               n_med=statistics.median(ns), n_max=max(ns), solo=sum(1 for x in ns if x == 1),
               winners=collections.Counter(r["winner"] for r in res).most_common(6))
dst = T / "result.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

print(f"{KEY}: всего состоявшихся {out['total']}, разобрано {out['parsed']}")
if res:
    print(f"  скидка: медиана {out['disc_med']}%  среднее {out['disc_avg']}%")
    print(f"  участников: медиана {out['n_med']}  макс {out['n_max']}  "
          f"лотов с одним {out['solo']}")
    print("  победители:", ", ".join(f"{w} ({c})" for w, c in out["winners"]))
    for r in res[:8]:
        print(f"   {r['lot']:<20} уч.{r['n']}  план {r['plan']:>10,.0f}  "
              f"победа {r['win']:>10,.0f}  −{r['disc']}%  {r['winner'][:22]}")
if skipped_single_source:
    print(f"  пропущено из одного источника: {skipped_single_source} "
          f"— приглашённый поставщик, торга нет")
print(f"\nстатистика ниши: {dst}", file=sys.stderr)
