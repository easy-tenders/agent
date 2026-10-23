---
title: executors — руки агента
type: registry
status: active
sensitivity: normal
scope: all
updated: 2026-10-23
related:
  - ../meta-vault/harness
  - automations
---

# Executors — руки агента

Агент один (`../CLAUDE.md` §Агент). Всё остальное — исполнители: делают шаг,
суждения не несут. Исполнитель не существует, пока его нет здесь. Закон —
`meta-vault/harness.md`.

| Исполнитель | Род | Где живёт | Что делает | Кто зовёт | Статус |
|---|---|---|---|---|---|
| `bin/check` | script | `bin/check` (python3, stdlib) | прогон: связи, имена, таблицы, секреты в индексе; только читает | [[../meta-vault/operations/check-links-and-names\|проверить базу]] | live |
| `bin/setup` | script | `bin/setup` (sh; macOS, Linux) | чистая машина: git, Python, `.venv` движка, `secrets/`, прогон check | первый запуск · [[../meta-vault/operations/add-engine\|завести движок]] | possible |
| `bin/setup.ps1` | script | `bin/setup.ps1` (PowerShell; Windows) | то же на Windows через winget, без прав администратора; длинные пути — предупреждает | первый запуск · [[../meta-vault/operations/add-engine\|завести движок]] | possible |
| `engine/scripts/collect_open.py` | script | `engine/` (python3, stdlib) | открытые лоты по слову с сайта портала (HTML), карточки, отсев истёкших | [[../tenders/tenders-vault/operations/naiti-loty\|найти лоты]] | live (прогон 23.10) |
| `engine/scripts/niche.py` · `winprice2.py` · `extract_docs.py` · `rating.py` | script | `engine/` | прошлые закупки и протоколы · скидка победителя · текст из документов · рейтинг лотов | [[../tenders/tenders-vault/operations/sobrat-otchet\|собрать отчёт]] · [[../tenders/tenders-vault/operations/otsenit-lot\|оценить лот]] | possible |
| `engine/scripts/ows.py` | script | `engine/` (python3, stdlib; токен в `secrets/goszakup-token`) | API портала по токену: лоты, договоры (кто выиграл), планы заказчиков, участник по БИН, справочники; `check` — диагностика доступа | [[../tenders/tenders-vault/operations/naiti-loty\|найти лоты]] · памятка [[../tenders/tenders-vault/tools/ows-api\|ows-api]] | possible — 403 с нашего адреса 23.10 |
| `engine/report/*.py` | script | `engine/report/` | PDF-отчёты — **не запускать**: исходники PDF от 25.07 с зашитым текстом | [[../tenders/tenders-vault/operations/sobrat-otchet\|собрать отчёт]] | off |

_(строка на каждый скилл, скрипт, суб-агент, MCP-сервер, канал; род:
skill · script · subagent · mcp · channel · cron; статус: possible · live · off)_
