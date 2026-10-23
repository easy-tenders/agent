# Шрифты отчётов

Лежат в репозитории нарочно: отчёт должен собираться одинаково на любой машине,
а не только там, где эти гарнитуры установлены в систему.

Обе — под **SIL Open Font License 1.1** (текст: `LICENSE-OFL.txt`). Лицензия
разрешает распространять шрифты в составе продукта; условия — сохранять
уведомления об авторских правах и не продавать сами шрифты отдельно.

| Файлы | Гарнитура | Авторские права |
|---|---|---|
| `Inter-Regular.ttf` · `Inter-SemiBold.ttf` · `Inter-ExtraBold.ttf` | Inter | Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter) |
| `PlayfairDisplay-SemiBold.ttf` · `PlayfairDisplay-SemiBoldItalic.ttf` | Playfair Display | Copyright 2017 The Playfair Display Project Authors (https://github.com/clauseggers/Playfair-Display), with Reserved Font Name "Playfair Display" |

Подключаются в `../maksi_style.py`. Если папка опустела —
`git checkout engine/report/fonts`.
