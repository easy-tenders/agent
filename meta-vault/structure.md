---
title: structure — состояние сборки неймспейса
type: status
status: active
sensitivity: normal
scope: all
updated: 2026-10-22
related:
  - vault-template
  - operations/check-links-and-names
  - operations/accept-new-version
---

# Структура — состояние сборки

Состояние **устройства** неймспейса, отдельно от состояния дел (дела — в
`status.md` доменов и `../planning/backlog.md`). Снимок, не журнал.

## Версия

- **Форма шаблона:** 2026-10-22 (первая строка журнала в [[vault-template]]).
- **Собран:** <дата сборки — операция [[operations/build-namespace|собрать неймспейс]]>
- **Владелец:** <имя> · **агент:** <имя>

## Здоровье (из прогона `bin/check`, с датой)

_(прогона ещё не было)_

## Расхождения с шаблоном

| Правило шаблона | Как здесь | Почему |
|---|---|---|

## Что просили, а мы не построили

**Дословно, словами владельца**, с датой и исходом (построено / нет / решили
не строить — почему). Самый ценный раздел: из него видно, чего базе не
хватало на деле.

_(пусто)_

## Уроки для шаблона

Что эта сборка узнала такого, что пригодится **любой** следующей: правило,
которого не было, форма, которая не подошла, шаг рецепта, который пришлось
обойти. Строка — дата · что · где в шаблоне это поправить. Отсюда уроки
поднимает тот, кто ведёт шаблон.

_(пусто)_

## Файлы метода (едут из шаблона при [[operations/accept-new-version|новой версии]])

`meta-vault/vault-template.md` · `meta-vault/principles.md` ·
`meta-vault/glossary.md` · `meta-vault/forms/` · `meta-vault/examples/` ·
`meta-vault/harness/` · `meta-vault/operations/build-namespace.md` ·
`new-domain.md` · `add-engine.md` · `check-links-and-names.md` ·
`accept-new-version.md` · `bin/check` · `bin/setup` · `bin/setup.ps1` ·
`.gitattributes`. Всё прочее — файлы владельца.

## Журнал сборки

Новое сверху; только устройство.

- 2026-10-22 — шаблон.
