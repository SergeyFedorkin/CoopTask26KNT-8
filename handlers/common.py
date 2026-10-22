from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from db import Database
from keyboards import main_kb

router = Router()
fallback = Router()   # подключается последним

HELP = """<b>📒 Бот-дневник</b>

<b>Расписание</b>
/today, /tomorrow, /week — пары (RUZ + твои ручные)
/group БПИ251 — подключить группу из RUZ (или email @edu.hse.ru — личное расписание с английским/майнором)
/addlesson пн 10:00-11:20 Английский @ 305 — еженедельная пара
/addlesson 25.10 18:00-19:30 Консультация — разовая
/lessons — список ручных пар

<b>Домашка</b>
/add — добавить пошагово (или кнопка ➕)
/add матан; №1.2–1.5; пт 18:00 — одной строкой
   срок: <code>завтра</code>, <code>пт</code>, <code>25.10</code>, <code>25.10 18:00</code>, <code>+3</code>, <code>через неделю</code>, <code>пара</code> (к следующей паре)
/hw — список, отметить ✅

<b>Оценки и накоп</b>
/formula Матан: КР 0.3, экзамен 0.5, ДЗ 0.2
/grade матан КР 5.6 — оценка (можно несколько: <code>ДЗ 8 9 7</code>)
/delgrade матан КР — убрать последнюю
/grades — накоп и сколько нужно на экзамене
/delsubject матан

<b>Настройки</b>
/settings — сводка по утрам, напоминания (по умолчанию за 24 ч и 3 ч)
/cancel — отменить текущий ввод"""


@router.message(CommandStart())
async def start(message: Message, db: Database, state: FSMContext):
    await state.clear()
    user = db.user(message.from_user.id)
    text = f"Привет, {message.from_user.first_name}! Я твой дневник: расписание, домашка, дедлайны, оценки.\n\n"
    if not user["ruz_id"]:
        text += "Для начала подключи расписание: пришли /group и название группы (например, <code>/group БПИ251</code>).\n\n"
    await message.answer(text + "Все команды — /help", reply_markup=main_kb)


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP, reply_markup=main_kb)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ок, отменил.", reply_markup=main_kb)


@fallback.message(F.text)
async def unknown(message: Message):
    await message.answer("Не понял 🤔 Жми кнопки внизу или смотри /help", reply_markup=main_kb)


@fallback.callback_query()
async def stale_button(callback: CallbackQuery):
    await callback.answer("Кнопка устарела — начни заново", show_alert=False)
