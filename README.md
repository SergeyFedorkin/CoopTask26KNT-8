# 📒 Бот-дневник (aiogram 3)

Командный проект по курсу «Технологии программирования».

Расписание из RUZ ВШЭ + ручные пары, ДЗ с дедлайнами и напоминаниями, утренняя сводка, оценки и накоп.

## Запуск

1. В Telegram у [@BotFather](https://t.me/BotFather): `/newbot` и скопируй токен.
2. Установи зависимости:
   ```bash
   cd diary_bot
   python -m venv venv
   venv\Scripts\activate          # Windows  (Linux/Mac: source venv/bin/activate)
   pip install -r requirements.txt
   ```
3. Скопируй `.env.example` в `.env` и вставь `BOT_TOKEN`. В `ALLOWED_USERS` впиши свой ID (узнать его можно у @userinfobot), чтобы ботом не пользовались чужие.
4. `python bot.py`
5. В боте: `/start`, потом `/group БПИ251` (или своя почта `…@edu.hse.ru`, тогда подтянется личное расписание с английским и майнором).

База `diary.db` создаётся сама рядом с `bot.py`.

## Что умеет

| | |
|---|---|
| `/group 26КНТ-8` | расписание из RUZ, а если он недоступен (открыт только из сети ВШЭ) — из Google-таблицы факультета; `/sheet 26КНТ-8` — сразу из таблицы |
| `/today` `/tomorrow` `/week` | пары с навигацией ◀️ ▶️, в том же сообщении дедлайны на этот день |
| `/add` или ➕ | ДЗ пошагово: предмет из кнопок → текст → срок (кнопка **«к следующей паре»** берёт дату из расписания) |
| `/add матан; №1–5; пт 18:00` | ДЗ одной строкой. Срок можно написать так: `завтра`, `пт`, `25.10 18:00`, `+3`, `через неделю`, `пара` |
| `/hw` | список ДЗ: 🔴 просрочено, 🟠 меньше суток, 🟡 меньше 3 дней; кнопки ✅, архив, удаление |
| напоминания | по умолчанию за 24 ч и 3 ч до дедлайна, меняется через `/remind 48 24 3` |
| сводка | каждое утро (по умолчанию в 07:30, меняется через `/summary 07:00` или `off`): пары, что сдать сегодня/завтра, просрочки |
| `/formula` `/grade` `/grades` | формула оценки, оценки, накоп и сколько нужно на оставшихся элементах для 4/6/8/10 |
| `/addlesson` `/lessons` | свои пары (еженедельные или разовые) |

## Сервер

Пошаговый деплой на два VPS с автодеплоем из GitHub описан в **[DEPLOY.md](DEPLOY.md)**. Если коротко: бот работает на российском сервере (там доступен RUZ), а в Telegram ходит через SSH-туннель на зарубежный.

Чтобы запустить локально в РФ, когда Telegram тормозит, пропиши в `.env` строку `TG_PROXY=socks5://...`.

## Команда

| Часть | Участник | Файлы |
|---|---|---|
| 1. Каркас и конфигурация | Матвей | `bot.py`, `config.py`, `requirements.txt`, `README.md` |
| 2. База данных | … | `db.py` |
| 3. Клиент RUZ и кэш расписания | … | `ruz.py`, `schedule_data.py` |
| 4. Даты, утилиты, клавиатуры | … | `utils.py`, `keyboards.py`, `handlers/tools.py` |
| 5. Расписание | … | `handlers/schedule.py`, `schedule_texts.py` |
| 6. Домашка | … | `handlers/homework.py`, `homework_logic.py` |
| 7. Оценки и накоп | … | `handlers/grades.py`, `grades_logic.py` |
| 8. Напоминания, сводка, настройки | … | `scheduler.py`, `summary.py`, `handlers/settings.py`, `handlers/common.py` |
| 9. Деплой и автодеплой | … | `deploy/`, `.github/workflows/deploy.yml`, `DEPLOY.md` |

Код подготовлен с помощью Claude (Anthropic) и распределён между участниками по согласованию с преподавателем.

## Структура

```
bot.py              запуск, роутеры, планировщик
config.py           чтение .env
db.py               SQLite (stdlib sqlite3)
ruz.py              клиент API RUZ
schedule_data.py    расписание: RUZ + кэш + ручные пары
schedule_texts.py   тексты «день» и «неделя»
homework_logic.py   статус и форматирование ДЗ, пороги напоминаний
grades_logic.py     формула оценки и расчёт накопа
summary.py          утренняя сводка
scheduler.py        фоновый цикл: напоминания + сводка (раз в 30 с)
keyboards.py        кнопки и callback-data
utils.py            парсинг дат и форматирование
handlers/           common, schedule, homework, grades, settings, tools
deploy/             скрипты сервера, systemd, update.sh
.github/            автодеплой (GitHub Actions)
```
