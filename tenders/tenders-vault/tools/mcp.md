---
type: reference
status: active
sensitivity: normal
scope: work
date: 2026-07-15
updated: 2026-07-15
tags: [tool, mcp, goszakup, samruk, api]
related:
  - portal
  - ../HOME
---

# MCP госзакупок — карта (данные напрямую)

Подключённый MCP-сервер по госзакупкам Казахстана. Основной инструмент для
**данных** (быстрее и структурированнее, чем клики). Два источника — держать
**раздельно**, не смешивать.

## Госзакуп (`goszakup.gov.kz`) — гос. закупки

- `search_goszakup_lots`, `get_goszakup_lot`, `goszakup_lot_detail` — поиск и
  детали лотов.
- `goszakup_announcement_detail` — детали объявления (тендера).
- `goszakup_lot_documents`, `read_goszakup_document` — документы, включая **ТЗ**.
- `goszakup_company_addresses`, `goszakup_company_employees` — по компании.
- `goszakup_filters` — доступные фильтры.

## Самрук (`zakup.sk.kz`) — квазигоссектор

- `search_samruk_lots`, `get_samruk_lot`, `read_samruk_document`, `samruk_filters`.
- Другая площадка: другие правила/сроки/данные. Показывать отдельным блоком.

## Кросс-данные (когда уместно)

- `search_plans` — годовые планы закупок (прогноз будущих тендеров).
- `treasury_payments` — фактические выплаты поставщикам (кто реально получает).
- `search_acts` — акты выполненных работ (суммы, штрафы, просрочки).
- `search_applications` — поданные ценовые предложения (конкуренция, история).
- `search_tenders` — объявления целиком.
- `search_contracts` — заключённые договоры.

## Правило

Все суммы — в тенге (₸). Если источник не указан владельцем — показать оба
(госзакуп и самрук) раздельно, явно подписав, где что.
