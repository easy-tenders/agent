#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ows.py — унифицированные сервисы портала госзакупок (ows.goszakup.gov.kz) по токену.

Замена разбору HTML-страниц портала там, где есть токен: ответы за секунды,
данные структурные (JSON), без ЭЦП. Памятка с полями и граблями —
tenders/tenders-vault/tools/ows-api.md. Внешних библиотек не требует.

Токен: переменная среды GOSZAKUP_TOKEN или файл secrets/goszakup-token в корне
базы (secrets/ вне git). Токен привязан к кабинету и, по практике, к IP-адресу,
указанному при выпуске: с чужого адреса портал отвечает 403.

Команды (запуск из любого места, пути считаются от корня базы):

  ows.py check                         — токен принят? доступ есть? (один запрос)
  ows.py lots <слово> [опции]          — открытые лоты по слову (название + описание,
                                         с морфологией); таблица + JSON в кэш
        --status 210,220,240             статусы лота (по умолчанию открытые)
        --kato 35                        место поставки, начало кода КАТО (35 = Карагандинская обл.); режется после выдачи
        --min 500000                     сумма лота от
        --all                            все статусы (история)
  ows.py lot <id>                      — лот подробно: объявление, заказчик, документы
  ows.py docs <id> [--to папка]        — документы лота и его объявления (техспецификация,
                                         проект договора) в папку; дальше extract_docs.py
  ows.py won <слово> [--year 2025]     — кто выигрывал: договоры по лотам с этим словом
  ows.py contracts --customer <БИН> | --supplier <БИН> [--year 2025]
  ows.py plans <слово> [--year 2026] [--bin <БИН заказчика>] — пункты годовых планов
  ows.py subject <БИН>                 — участник: имя, КАТО, признаки
  ows.py refs <справочник> [--find слово]  — справочник целиком (ref_lots_status, ref_trade_methods, ref_kato …)
  ows.py selftest                      — разбор и таблицы на встроенном примере, без сети

Пагинация GraphQL: limit ≤ 200, следующая страница — after = lastId из
extensions.pageInfo. Поиск по тексту: «*слово» — с морфологией, «?слово» — часть
слова без морфологии, «слово» — точное совпадение.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HOST = "https://ows.goszakup.gov.kz"
GQL = HOST + "/v3/graphql"
REST = HOST + "/v2"
PAUSE = 0.3
BACKOFF = (10, 30, 60)
OPEN_STATUSES = [210, 220, 240]      # как у поиска по HTML: опубликован · приём заявок · продлён
PAGE = 200

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")   # Windows: кириллица в консоли


# ---------- токен и сеть ----------

def base_dir():
    return Path(__file__).resolve().parent.parent.parent


def token():
    t = os.environ.get("GOSZAKUP_TOKEN", "").strip()
    if t:
        return t
    f = base_dir() / "secrets" / "goszakup-token"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    sys.exit("нет токена: положите его в secrets/goszakup-token (вне git) "
             "или в переменную GOSZAKUP_TOKEN")


class AccessError(Exception):
    pass


_last = 0.0


def _request(url, body=None):
    """Один HTTP-запрос с паузой и повтором на 429. Возвращает (код, json|текст)."""
    global _last
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": "Bearer " + token(),
               "Content-Type": "application/json",
               "User-Agent": "easy-tender-agent/ows.py"}
    for attempt in range(len(BACKOFF) + 1):
        wait = PAUSE - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                code = resp.status
        except urllib.error.HTTPError as e:
            raw = e.read()
            code = e.code
        except (urllib.error.URLError, OSError) as e:
            sys.exit(f"портал недоступен: {e}")
        _last = time.monotonic()
        if code == 429 and attempt < len(BACKOFF):
            print(f"  портал: слишком много запросов — жду {BACKOFF[attempt]} с", file=sys.stderr)
            time.sleep(BACKOFF[attempt])
            continue
        try:
            return code, json.loads(raw.decode("utf-8"))
        except ValueError:
            return code, raw.decode("utf-8", "replace")
    return code, raw.decode("utf-8", "replace")


def explain(code, payload):
    """Человеческое объяснение отказа портала."""
    msg = payload.get("message") if isinstance(payload, dict) else str(payload)[:200]
    if code == 401:
        return ("401 — токен не принят (просрочен, опечатка или не тот). Перевыпуск: "
                "кабинет портала → Профиль участника → Выпуск токена (для разработчиков).")
    if code == 403:
        return ("403 — токен принят, но запрос с этого адреса запрещён: токен привязан к "
                "IP-адресу, указанному при выпуске. Запускать с той машины или добавить "
                "свой адрес в кабинете при перевыпуске. Ответ портала: " + str(msg))
    return f"{code} — {msg}"


def gql(query, variables):
    code, payload = _request(GQL, {"query": query, "variables": variables})
    if code != 200:
        raise AccessError(explain(code, payload))
    if isinstance(payload, dict) and payload.get("errors"):
        raise AccessError("GraphQL: " + "; ".join(e.get("message", "?") for e in payload["errors"]))
    return payload


def gql_all(name, query, variables, limit=None):
    """Собрать все страницы запроса `name` (Lots, TrdBuy, Contract, Plans, Subjects)."""
    items, after, total = [], None, None
    while True:
        v = dict(variables, limit=PAGE, after=after)
        payload = gql(query, v)
        chunk = (payload.get("data") or {}).get(name) or []
        info = (payload.get("extensions") or {}).get("pageInfo") or {}
        total = info.get("totalCount", total)
        items.extend(chunk)
        if limit and len(items) >= limit:
            return items[:limit], total
        if not chunk or not info.get("hasNextPage") or not info.get("lastId"):
            return items, total
        after = info["lastId"]


def rest(path):
    code, payload = _request(REST + path)
    if code != 200:
        raise AccessError(explain(code, payload))
    return payload


# ---------- разбор и печать ----------

def money(x):
    try:
        return f"{float(x):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def date_short(s):
    if not s:
        return "—"
    return s[:16]


def single_source(lot):
    """«Из одного источника» — по имени способа закупки; такие лоты поставщику закрыты."""
    tb = lot.get("TrdBuy") or {}
    names = [(lot.get("RefBuyTradeMethods") or {}).get("nameRu") or "",
             (lot.get("RefTradeMethods") or {}).get("nameRu") or "",
             (tb.get("RefTradeMethods") or {}).get("nameRu") or ""]
    return any("одного источника" in n.lower() for n in names) or bool(tb.get("biinSupplier"))


def lot_rows(lots):
    """Строки таблицы: номер · кол-во × цена = сумма · срок · заказчик · название."""
    rows = []
    for l in lots:
        tb = l.get("TrdBuy") or {}
        cnt = l.get("count") or 0
        amt = l.get("amount") or 0
        price = amt / cnt if cnt else 0
        rows.append({
            "id": l.get("id"), "lot": l.get("lotNumber"), "anno": l.get("trdBuyNumberAnno"),
            "count": cnt, "price": price, "amount": amt,
            "end": tb.get("endDate"), "status": l.get("refLotStatusId"),
            "method": (l.get("RefBuyTradeMethods") or l.get("RefTradeMethods") or {}).get("nameRu"),
            "customer": l.get("customerNameRu") or tb.get("customerNameRu"),
            "kato": ",".join(l.get("plnPointKatoList") or []),
            "name": l.get("nameRu"), "desc": (l.get("descriptionRu") or "")[:90],
            "single": single_source(l),
        })
    rows.sort(key=lambda r: (r["end"] or "9999", -r["amount"]))
    return rows


def print_lots(rows, title):
    print(f"\n{title}: {len(rows)}")
    if not rows:
        return
    print(f"{'лот':<14} {'кол-во × цена = сумма ₸':>34}  {'приём до':<16} {'способ':<22} заказчик · название")
    for r in rows:
        line = (f"{str(r['lot']):<14} {r['count']:>7.1f} × {money(r['price']):>10} = {money(r['amount']):>11}  "
                f"{date_short(r['end']):<16} {(r['method'] or '—')[:22]:<22} "
                f"{(r['customer'] or '—')[:40]} · {(r['name'] or '')[:60]}")
        print(line)


def expired(row, now=None):
    now = now or datetime.now()
    try:
        return datetime.strptime(row["end"][:19], "%Y-%m-%d %H:%M:%S") < now
    except (TypeError, ValueError):
        return False


def cache_write(tag, obj):
    import tempfile
    d = Path(tempfile.gettempdir()) / "tender-agent" / "ows"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{tag}.json"
    f.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return f


# ---------- запросы ----------

LOT_FIELDS = """
  id lotNumber refLotStatusId nameRu descriptionRu count amount customerBin customerNameRu
  trdBuyId trdBuyNumberAnno refTradeMethodsId refBuyTradeMethodsId plnPointKatoList
  dumping lastUpdateDate
  RefLotsStatus { nameRu }
  RefTradeMethods { nameRu }
  RefBuyTradeMethods { nameRu }
  TrdBuy { numberAnno nameRu startDate endDate publishDate refBuyStatusId refTradeMethodsId
           customerNameRu orgNameRu orgBin biinSupplier totalSum
           RefTradeMethods { nameRu } }
"""
LOT_FILES = "  Files { nameRu originalName filePath }\n"

Q_LOTS = "query($limit:Int,$after:Int,$filter:LotsFiltersInput){ Lots(limit:$limit, after:$after, filter:$filter){" + LOT_FIELDS + "} }"
Q_LOT = "query($limit:Int,$after:Int,$filter:LotsFiltersInput){ Lots(limit:$limit, after:$after, filter:$filter){" + LOT_FIELDS + LOT_FILES + "} }"
Q_CONTRACTS = """query($limit:Int,$after:Int,$filter:ContractFiltersInput){ Contract(limit:$limit, after:$after, filter:$filter){
  id contractNumber contractNumberSys trdBuyId trdBuyNumberAnno trdBuyNameRu refContractStatusId
  crdate signDate finYear contractSum contractSumWnds faktSumWnds supplierBiin supplierId customerBin customerId
  faktTradeMethodsId descriptionRu
  Supplier { nameRu bin }
  Customer { nameRu bin }
} }"""
Q_CONTRACTS_PLAIN = Q_CONTRACTS.replace("  Supplier { nameRu bin }\n  Customer { nameRu bin }\n", "")
Q_PLANS = """query($limit:Int,$after:Int,$filter:PlansFiltersInput){ Plans(limit:$limit, after:$after, filter:$filter){
  id plnPointYear subjectBiin subjectNameRu nameRu descRu extraDescRu count price amount
  refMonthsId refTradeMethodsId refPlnPointStatusId refEnstruCode supplyDateRu
  RefTradeMethods { nameRu } RefMonths { nameRu } RefPlnPointStatus { nameRu }
  PlansKato { refKatoCode fullDeliveryPlaceNameRu }
} }"""
Q_PLANS_PLAIN = Q_PLANS.replace("  PlansKato { refKatoCode fullDeliveryPlaceNameRu }\n", "")
Q_SUBJECT = """query($limit:Int,$after:Int,$filter:SubjectFiltersInput){ Subjects(limit:$limit, after:$after, filter:$filter){
  pid bin iin nameRu fullNameRu regdate katoList website customer supplier qvazi
  markSmallEmployer markNationalCompany markPatronymicProducer okedList
  Address { address katoCode }
} }"""
Q_SUBJECT_PLAIN = Q_SUBJECT.replace("  Address { address katoCode }\n", "")


def text_filter(word):
    """Слово владельца → фильтр портала. Со звёздочкой — морфология; «?» — часть слова."""
    w = word.strip()
    if w[:1] in "*?":
        return w
    return "*" + w


def search_lots(f, word, limit=None):
    """Поиск с морфологией по названию и описанию; портал глух к редким словам
    («гидротехнические» → 0) — тогда повтор подстрокой по названию (`?слово`),
    по первым 7 буквам каждого слова. Возвращает (лоты, всего, режим)."""
    lots, total = gql_all("Lots", Q_LOTS, {"filter": f}, limit=limit)
    if lots or word.strip()[:1] in "*?":
        return lots, total, "морфология"
    stems = [w[:7].lower() for w in word.split() if len(w) > 2] or [word.lower()]
    f2 = dict(f); f2.pop("nameDescriptionRu", None); f2["nameRu"] = "?" + stems[0]
    lots, total = gql_all("Lots", Q_LOTS, {"filter": f2}, limit=limit)
    if len(stems) > 1:   # остальные слова — по названию и описанию, у себя
        lots = [l for l in lots if all(s in ((l.get("nameRu") or "") + " " + (l.get("descriptionRu") or "")).lower() for s in stems[1:])]
    return lots, len(lots), f"подстрока «{stems[0]}» в названии лота" + (f" + {stems[1:]} в тексте" if len(stems) > 1 else "")


Q_TB = """query($limit:Int,$after:Int,$filter:TrdBuyFiltersInput){ TrdBuy(limit:$limit, after:$after, filter:$filter){
  id numberAnno nameRu totalSum startDate endDate publishDate refBuyStatusId customerNameRu orgNameRu kato
  RefTradeMethods { nameRu } } }"""


def announcements(word, since="2026-01-01"):
    """Работы и услуги часто названы в объявлении, а не в лоте: ищем подстрокой по
    названию объявления, остальные слова — у себя. Возвращает объявления, у которых
    приём ещё идёт."""
    stems = [w[:7].lower() for w in word.split() if len(w) > 2] or [word.lower()]
    items, _ = gql_all("TrdBuy", Q_TB, {"filter": {"nameRu": "?" + stems[0], "lastUpdateDate": [since]}}, limit=1000)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [t for t in items if all(s in (t.get("nameRu") or "").lower() for s in stems[1:])
           and (t.get("endDate") or "") >= now]
    out.sort(key=lambda t: (t.get("endDate") or "", -(t.get("totalSum") or 0)))
    return out


def print_announcements(items):
    print(f"\nобъявления с таким названием, приём идёт: {len(items)}")
    for t in items:
        print(f"{t.get('numberAnno'):<13} {money(t.get('totalSum')):>14} ₸  до {date_short(t.get('endDate')):<16} "
              f"{((t.get('RefTradeMethods') or {}).get('nameRu') or '—')[:22]:<22} КАТО {','.join(t.get('kato') or [])[:11]:<11} "
              f"{(t.get('customerNameRu') or t.get('orgNameRu') or '—')[:40]} · {(t.get('nameRu') or '')[:90]}")


def cmd_check(args):
    try:
        payload = gql("query($limit:Int){ Lots(limit:$limit){ id } }", {"limit": 1})
    except AccessError as e:
        print("доступа нет:", e)
        return 1
    info = (payload.get("extensions") or {}).get("pageInfo") or {}
    print(f"доступ есть: реестр лотов отвечает, всего записей {info.get('totalCount', '?')}")
    return 0


def cmd_lots(args):
    f = {"nameDescriptionRu": text_filter(args.word)}
    if not getattr(args, "all", False):
        f["refLotStatusId"] = [int(s) for s in args.status.split(",")]
    if args.min:
        f["amount"] = [float(args.min)]
    lots, total, mode = search_lots(f, args.word)
    if args.kato:   # портал фильтрует КАТО только по точному коду — режем по началу сами
        lots = [l for l in lots if any(str(k).startswith(args.kato) for k in (l.get("plnPointKatoList") or []))]
    rows = lot_rows(lots)
    live = [r for r in rows if not expired(r)] if not getattr(args, "all", False) else rows
    gone = len(rows) - len(live)
    avail = [r for r in live if not r["single"]]
    single = [r for r in live if r["single"]]
    print(f"лотов по «{args.word}» в выдаче портала: {total if total is not None else len(rows)} ({mode}); "
          f"получено {len(rows)}" + (f", в регионе {args.kato}* — {len(lots)}" if args.kato else "") + f"; срок приёма прошёл — {gone}")
    print_lots(avail, "доступные")
    print_lots(single, "из одного источника — участвовать нельзя, показываем отдельно")
    anns = announcements(args.word)
    if args.kato:
        anns = [t for t in anns if any(str(k).startswith(args.kato) for k in (t.get("kato") or []))]
    if anns:
        print_announcements(anns)
    f_out = cache_write("lots_" + "".join(c for c in args.word if c.isalnum())[:30], {"lots": lots, "announcements": anns})
    print(f"\nданные лотов: {f_out}")
    return 0


def cmd_lot(args):
    lots, _ = gql_all("Lots", Q_LOT, {"filter": {"id": [int(args.id)]}}, limit=1)
    if not lots:
        print("лот не найден")
        return 1
    l = lots[0]
    tb = l.get("TrdBuy") or {}
    print(f"лот {l.get('lotNumber')} (id {l.get('id')}) · статус {l.get('refLotStatusId')} "
          f"{(l.get('RefLotsStatus') or {}).get('nameRu') or ''}")
    print(f"  {l.get('nameRu')}")
    print(f"  описание: {l.get('descriptionRu')}")
    print(f"  кол-во {l.get('count')} · сумма {money(l.get('amount'))} ₸ · демпинг {l.get('dumping')}")
    print(f"  заказчик: {l.get('customerNameRu')} (БИН {l.get('customerBin')}) · КАТО {l.get('plnPointKatoList')}")
    print(f"  объявление {tb.get('numberAnno')}: {tb.get('nameRu')}")
    print(f"    способ: {(tb.get('RefTradeMethods') or {}).get('nameRu')} · статус {tb.get('refBuyStatusId')}")
    print(f"    приём заявок: {date_short(tb.get('startDate'))} → {date_short(tb.get('endDate'))} · "
          f"опубликовано {date_short(tb.get('publishDate'))}")
    print(f"    организатор: {tb.get('orgNameRu')} (БИН {tb.get('orgBin')})")
    if tb.get("biinSupplier"):
        print(f"    поставщик из одного источника: {tb.get('biinSupplier')}")
    files = l.get("Files") or []
    print(f"  документы лота: {len(files)}")
    for f in files:
        print(f"    - {f.get('nameRu')}: {f.get('originalName')} → {f.get('filePath')}")
    print(f"  страница: https://old.goszakup.gov.kz/ru/announce/index/{tb.get('numberAnno', '').split('-')[0]}"
          if tb.get("numberAnno") else "")
    return 0


Q_TB_FILES = """query($limit:Int,$after:Int,$filter:TrdBuyFiltersInput){ TrdBuy(limit:$limit, after:$after, filter:$filter){
  id numberAnno nameRu Files { nameRu originalName filePath } } }"""


def _download(url, dest):
    """Файл по ссылке из API. Документы лежат открыто — без токена (проверено 23.10)."""
    global _last
    wait = PAUSE - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": "easy-tender-agent/ows.py"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            dest.write_bytes(resp.read())
    except (urllib.error.URLError, OSError) as e:
        print(f"  не скачалось: {url} — {e}", file=sys.stderr)
        return False
    finally:
        _last = time.monotonic()
    return dest.stat().st_size > 0


def cmd_docs(args):
    """Документы лота и его объявления: у лота лежит техспецификация, у объявления —
    она же и проект договора. Папка — аргумент или временная папка прогона."""
    lots, _ = gql_all("Lots", Q_LOT, {"filter": {"id": [int(args.id)]}}, limit=1)
    if not lots:
        print("лот не найден")
        return 1
    l = lots[0]
    files = list(l.get("Files") or [])
    if l.get("trdBuyId"):
        tbs, _ = gql_all("TrdBuy", Q_TB_FILES, {"filter": {"id": [int(l["trdBuyId"])]}}, limit=1)
        for tb in tbs:
            files.extend(tb.get("Files") or [])
    import tempfile
    out = Path(args.to) if args.to else (Path(tempfile.gettempdir()) / "tender-agent" / "ows"
                                         / f"docs_{l.get('lotNumber')}")
    out.mkdir(parents=True, exist_ok=True)
    seen, got = set(), 0
    for f in files:
        name = Path(f.get("originalName") or Path(f.get("filePath") or "").name).name
        if not f.get("filePath") or not name or name in seen:
            continue
        seen.add(name)
        dest = out / name
        ok = (dest.exists() and dest.stat().st_size > 0) or _download(f["filePath"], dest)
        got += bool(ok)
        print(f"  {'+' if ok else '-'} {f.get('nameRu')}: {name}")
    print(f"документы лота {l.get('lotNumber')}: {got} из {len(seen)} → {out}")
    print(f"текст из них: python3 engine/scripts/extract_docs.py \"{out}\"  (ляжет в {out / '_text'})")
    return 0 if seen and got == len(seen) else 1


def _contracts(filter_, limit=None):
    try:
        return gql_all("Contract", Q_CONTRACTS, {"filter": filter_}, limit=limit)
    except AccessError as e:
        if "Supplier" in str(e) or "Customer" in str(e):
            return gql_all("Contract", Q_CONTRACTS_PLAIN, {"filter": filter_}, limit=limit)
        raise


def print_contracts(items):
    print(f"договоров: {len(items)}")
    print(f"{'подписан':<11} {'сумма ₸':>13}  {'поставщик':<42} {'заказчик':<36} объявление")
    for c in sorted(items, key=lambda c: c.get("signDate") or c.get("crdate") or "", reverse=True):
        sup = (c.get("Supplier") or {}).get("nameRu") or c.get("supplierBiin") or "—"
        cus = (c.get("Customer") or {}).get("nameRu") or c.get("customerBin") or "—"
        print(f"{(c.get('signDate') or c.get('crdate') or '—')[:10]:<11} {money(c.get('contractSumWnds')):>13}  "
              f"{sup[:42]:<42} {cus[:36]:<36} {c.get('trdBuyNumberAnno') or '—'} · {(c.get('trdBuyNameRu') or '')[:50]}")


def cmd_won(args):
    """Прошлые закупки по слову: лоты любого статуса → договоры по их объявлениям."""
    f = {"nameDescriptionRu": text_filter(args.word)}
    if args.year:
        f["lastUpdateDate"] = [f"{args.year}-01-01", f"{args.year}-12-31"]
    lots, total, mode = search_lots(f, args.word, limit=args.limit)
    if args.kato:
        lots = [l for l in lots if any(str(k).startswith(args.kato) for k in (l.get("plnPointKatoList") or []))]
    ids = sorted({l["trdBuyId"] for l in lots if l.get("trdBuyId")})
    print(f"лотов по «{args.word}»: {total} ({mode}); взято {len(lots)}, объявлений {len(ids)}")
    contracts = []
    for i in range(0, len(ids), 50):
        part, _ = _contracts({"trdBuyId": ids[i:i + 50]})
        contracts.extend(part)
    print_contracts(contracts)
    # сводка по поставщикам
    by = {}
    for c in contracts:
        k = (c.get("Supplier") or {}).get("nameRu") or c.get("supplierBiin") or "—"
        by.setdefault(k, [0, 0.0])
        by[k][0] += 1
        by[k][1] += float(c.get("contractSumWnds") or 0)
    if by:
        print("\nкто берёт чаще всего:")
        for k, (n, s) in sorted(by.items(), key=lambda kv: -kv[1][1])[:15]:
            print(f"  {n:>3} дог. · {money(s):>13} ₸ · {k}")
    f_out = cache_write("won_" + "".join(c for c in args.word if c.isalnum())[:30],
                        {"lots": lots, "contracts": contracts})
    print(f"\nданные: {f_out}")
    return 0


def cmd_contracts(args):
    f = {}
    if args.customer:
        f["customerBin"] = args.customer
    if args.supplier:
        f["supplierBiin"] = args.supplier
    if not f:
        sys.exit("нужен --customer <БИН> или --supplier <БИН>")
    if args.year:
        f["finYear"] = int(args.year)
    items, total = _contracts(f, limit=args.limit)
    print(f"всего в реестре: {total}")
    print_contracts(items)
    return 0


def cmd_plans(args):
    f = {"nameDescriptionRu": text_filter(args.word)}
    if args.year:
        f["plnPointYear"] = [int(args.year)]
    if args.bin:
        f["subjectBiin"] = args.bin
    try:
        items, total = gql_all("Plans", Q_PLANS, {"filter": f}, limit=args.limit)
    except AccessError as e:
        if "PlansKato" in str(e) or "Kato" in str(e):
            items, total = gql_all("Plans", Q_PLANS_PLAIN, {"filter": f}, limit=args.limit)
        else:
            raise
    print(f"пунктов плана по «{args.word}»: {total}; получено {len(items)}")
    print(f"{'год':<5} {'месяц':<9} {'кол-во × цена = сумма ₸':>34}  {'способ':<22} заказчик · предмет")
    for p in sorted(items, key=lambda p: -(p.get("amount") or 0)):
        kato = ", ".join((k.get("fullDeliveryPlaceNameRu") or k.get("refKatoCode") or "")
                         for k in (p.get("PlansKato") or []))[:40]
        print(f"{p.get('plnPointYear') or '—':<5} {((p.get('RefMonths') or {}).get('nameRu') or '—')[:9]:<9} "
              f"{(p.get('count') or 0):>7.1f} × {money(p.get('price')):>10} = {money(p.get('amount')):>11}  "
              f"{((p.get('RefTradeMethods') or {}).get('nameRu') or '—')[:22]:<22} "
              f"{(p.get('subjectNameRu') or '—')[:40]} · {(p.get('nameRu') or '')[:50]}"
              + (f" · {kato}" if kato else ""))
    f_out = cache_write("plans_" + "".join(c for c in args.word if c.isalnum())[:30], items)
    print(f"\nданные: {f_out}")
    return 0


def cmd_subject(args):
    f = {"bin": args.bin} if len(args.bin) == 12 and not args.iin else {"iin": args.bin}
    try:
        items, _ = gql_all("Subjects", Q_SUBJECT, {"filter": f}, limit=5)
    except AccessError as e:
        if "Address" in str(e):
            items, _ = gql_all("Subjects", Q_SUBJECT_PLAIN, {"filter": f}, limit=5)
        else:
            raise
    if not items:
        print("участник не найден")
        return 1
    for s in items:
        print(f"{s.get('nameRu')} · БИН/ИИН {s.get('bin') or s.get('iin')} · pid {s.get('pid')}")
        print(f"  полное: {s.get('fullNameRu')}")
        print(f"  зарегистрирован {date_short(s.get('regdate'))} · КАТО {s.get('katoList')} · сайт {s.get('website') or '—'}")
        print(f"  заказчик {s.get('customer')} · поставщик {s.get('supplier')} · квази {s.get('qvazi')} · "
              f"малый {s.get('markSmallEmployer')} · отеч. производитель {s.get('markPatronymicProducer')}")
        for a in s.get("Address") or []:
            print(f"  адрес: {a.get('address')} ({a.get('katoCode')})")
    return 0


def cmd_refs(args):
    name = args.name if args.name.startswith("ref_") else "ref_" + args.name
    items, page = [], f"/refs/{name}"
    while page:
        payload = rest(page)
        items.extend(payload.get("items") or [])
        page = payload.get("next_page") or ""
        if page.startswith("/v2"):
            page = page[3:]
    print(f"{name}: {len(items)}")
    for it in items:
        line = f"  {it.get('id') or it.get('code'):>6}  {it.get('name_ru') or it.get('name') or ''}"
        if it.get("code") and it.get("id"):
            line += f"  [{it.get('code')}]"
        if not args.find or args.find.lower() in line.lower():
            print(line)
    return 0


# ---------- офлайн-проверка разбора ----------

SAMPLE = [
    {"id": 1, "lotNumber": "88356423-ЗЦП1", "refLotStatusId": 220, "nameRu": "Кондиционер",
     "descriptionRu": "настенный, площадь охлаждения более 50 м2", "count": 6, "amount": 1189655,
     "customerBin": "000000000000", "customerNameRu": "Поликлиника №1 г. Караганды",
     "trdBuyId": 10, "trdBuyNumberAnno": "88356423-1", "plnPointKatoList": ["351010000"],
     "RefBuyTradeMethods": {"nameRu": "Запрос ценовых предложений"},
     "TrdBuy": {"numberAnno": "88356423-1", "endDate": "2099-10-27 00:00:00", "customerNameRu": "Поликлиника №1 г. Караганды"}},
    {"id": 2, "lotNumber": "88311598-ОИ2", "refLotStatusId": 210, "nameRu": "Кондиционер",
     "descriptionRu": "настенный", "count": 5, "amount": 1500000, "trdBuyId": 11,
     "trdBuyNumberAnno": "88311598-2", "plnPointKatoList": ["711310000"],
     "RefBuyTradeMethods": {"nameRu": "Из одного источника по несостоявшимся закупкам"},
     "TrdBuy": {"numberAnno": "88311598-2", "endDate": "2099-10-23 23:06:00", "biinSupplier": "111111111111"}},
    {"id": 3, "lotNumber": "80000001-ЗЦП1", "refLotStatusId": 220, "nameRu": "Кондиционер",
     "descriptionRu": "срок прошёл", "count": 1, "amount": 100000, "trdBuyId": 12,
     "trdBuyNumberAnno": "80000001-1", "TrdBuy": {"numberAnno": "80000001-1", "endDate": "2020-01-01 00:00:00"}},
]


def cmd_selftest(args):
    rows = lot_rows(SAMPLE)
    assert len(rows) == 3
    live = [r for r in rows if not expired(r)]
    assert len(live) == 2, live
    assert [r["single"] for r in live] == [True, False], live   # ближайший срок первым
    assert abs(live[1]["price"] - 198275.8) < 1
    print_lots([r for r in live if not r["single"]], "доступные")
    print_lots([r for r in live if r["single"]], "из одного источника")
    assert text_filter("кондиционер") == "*кондиционер" and text_filter("?конд") == "?конд"
    assert money(1189655) == "1 189 655"
    print("\nselftest: разбор, отсев по сроку, деление на доступные и «из одного источника», "
          "цена за единицу — ок")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("lots"); p.add_argument("word")
    p.add_argument("--status", default=",".join(map(str, OPEN_STATUSES)))
    p.add_argument("--kato"); p.add_argument("--min"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("lot"); p.add_argument("id")
    p = sub.add_parser("docs"); p.add_argument("id"); p.add_argument("--to")
    p = sub.add_parser("won"); p.add_argument("word"); p.add_argument("--year")
    p.add_argument("--kato"); p.add_argument("--limit", type=int, default=400)
    p = sub.add_parser("contracts"); p.add_argument("--customer"); p.add_argument("--supplier")
    p.add_argument("--year"); p.add_argument("--limit", type=int, default=200)
    p = sub.add_parser("plans"); p.add_argument("word"); p.add_argument("--year")
    p.add_argument("--bin"); p.add_argument("--limit", type=int, default=400)
    p = sub.add_parser("subject"); p.add_argument("bin"); p.add_argument("--iin", action="store_true")
    p = sub.add_parser("refs"); p.add_argument("name"); p.add_argument("--find")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    fn = globals()["cmd_" + args.cmd]
    try:
        return fn(args)
    except AccessError as e:
        print("портал отказал:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
