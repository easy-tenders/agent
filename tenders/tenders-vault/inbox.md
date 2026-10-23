---
title: inbox/ — приёмник выгрузок домена tenders
type: index
status: active
sensitivity: private
scope: work
axis: vault
date: 2026-07-15
updated: 2026-07-15
tags: [inbox, capture, intake, gpt-dump]
related:
  - ../status
  - ../HOME
---

# inbox/ — сырой захват (в т.ч. выгрузка из GPT)

Дверь захвата домена tenders: сюда падает сырьё до разбора — дамп из GPT,
случайные находки по лотам, ссылки, куски ТЗ. Один файл `YYYY-MM-DD-<slug>.md`,
ноль церемоний.

**Приватность:** содержимое этой папки — **вне git** (`.gitignore`: `inbox/*`,
кроме `README.md`). Так дампы с личными/чувствительными данными не утекают в
историю репозитория. Трекается только это описание.

## Как разбирать

Не хранилище. На регулярной сессии каждый пункт уходит в целевую зону и
оставляет след:

- устойчивый факт/разбор лота → `research/`;
- заказчик/конкурент → `market/`;
- контрагент-человек → `people/` (или общий `../../meta-vault/people/`);
- решение «участвуем/нет и почему» → `research/` разбор + при надобности
  прецедент в `decisions/`.

## Живое

- `2026-07-15-gpt-dump.md` — **разобран** (2026-07-15): 8 позиций →
  , вендоры →
  [[suppliers/suppliers-vault/HOME|suppliers/]], термины →
  [[tenders/reference/glossary|reference/glossary]], процесс →
  [[tenders/tenders-vault/workflow|workflow]]. Файл помечен «продолжение
  следует» — ждём доп. часть, дописывать сюда же.
