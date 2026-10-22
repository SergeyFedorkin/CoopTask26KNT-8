import re
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import Database
from handlers.tools import edit
from keyboards import BTN_TODAY, BTN_TOMORROW, BTN_WEEK, DayCb, LessonCb, WeekCb, btn, day_nav, week_nav
from ruz import Ruz
from schedule_texts import day_text, week_text
from utils import WD_SHORT, parse_date, parse_hhmm, parse_weekday, q, today

router = Router()


def _day_markup(d: date):
    return day_nav((d - timedelta(days=1)).isoformat(), (d + timedelta(days=1)).isoformat(), today().isoformat())


def _week_markup(monday: date):
    cur = today() - timedelta(days=today().weekday())
    return week_nav((monday - timedelta(days=7)).isoformat(), (monday + timedelta(days=7)).isoformat(), cur.isoformat())


async def _send_day(message: Message, db: Database, ruz: Ruz, d: date):
    await message.bot.send_chat_action(message.chat.id, "typing")
    await message.answer(await day_text(db, ruz, message.from_user.id, d), reply_markup=_day_markup(d))


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def show_today(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await state.clear()
    await _send_day(message, db, ruz, today())


@router.message(Command("tomorrow"))
@router.message(F.text == BTN_TOMORROW)
async def show_tomorrow(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await state.clear()
    await _send_day(message, db, ruz, today() + timedelta(days=1))


@router.message(Command("week"))
@router.message(F.text == BTN_WEEK)
async def show_week(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await state.clear()
    await message.bot.send_chat_action(message.chat.id, "typing")
    monday = today() - timedelta(days=today().weekday())
    await message.answer(await week_text(db, ruz, message.from_user.id, monday), reply_markup=_week_markup(monday))


@router.callback_query(DayCb.filter())
async def nav_day(callback: CallbackQuery, callback_data: DayCb, db: Database, ruz: Ruz):
    d = date.fromisoformat(callback_data.d)
    await edit(callback, await day_text(db, ruz, callback.from_user.id, d), _day_markup(d))
    await callback.answer()


@router.callback_query(WeekCb.filter())
async def nav_week(callback: CallbackQuery, callback_data: WeekCb, db: Database, ruz: Ruz):
    monday = date.fromisoformat(callback_data.d)
    await edit(callback, await week_text(db, ruz, callback.from_user.id, monday), _week_markup(monday))
    await callback.answer()


# ---------------- ручные пары ----------------
ADD_LESSON_RE = re.compile(r"(\S+)\s+(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})\s+(.+)")


@router.message(Command("addlesson"))
async def add_lesson(message: Message, command: CommandObject, db: Database):
    usage = ("Формат:\n<code>/addlesson пн 10:00-11:20 Английский @ 305</code> — каждую неделю\n"
             "<code>/addlesson 25.10 18:00-19:30 Консультация</code> — один раз")
    m = ADD_LESSON_RE.fullmatch((command.args or "").strip())
    if not m:
        return await message.answer(usage)
    day_tok, t_from, t_to, rest = m.groups()
    t_from, t_to = parse_hhmm(t_from), parse_hhmm(t_to)
    if not t_from or not t_to or t_from >= t_to:
        return await message.answer("Время кривое. " + usage)
    title, _, room = rest.partition("@")
    title, room = title.strip(), room.strip()

    weekday = parse_weekday(day_tok)
    one_day = None if weekday is not None else parse_date(day_tok, today())
    if weekday is None and one_day is None:
        return await message.answer("Не понял день. " + usage)

    db.add_lesson(message.from_user.id, weekday, one_day.isoformat() if one_day else None, t_from, t_to, title, room)
    when = f"каждый {WD_SHORT[weekday]}" if weekday is not None else one_day.strftime("%d.%m.%Y")
    await message.answer(f"✍️ Добавил: <b>{q(title)}</b>, {when} {t_from}–{t_to}" + (f", {q(room)}" if room else ""))


def lessons_view(db: Database, uid: int):
    rows = db.lessons_all(uid)
    if not rows:
        return "Ручных пар нет. Добавить: /addlesson", None
    lines = ["✍️ <b>Ручные пары</b> (нажми, чтобы удалить):"]
    kb = InlineKeyboardBuilder()
    for n, r in enumerate(rows, 1):
        when = WD_SHORT[r["weekday"]] if r["weekday"] is not None else date.fromisoformat(r["day"]).strftime("%d.%m")
        room = f" · {q(r['room'])}" if r["room"] else ""
        lines.append(f"{n}. {when} {r['time_from']}–{r['time_to']} {q(r['title'])}{room}")
        kb.add(btn(f"🗑 {n}", LessonCb(id=r["id"])))
    kb.adjust(5)
    return "\n".join(lines), kb.as_markup()


@router.message(Command("lessons"))
async def list_lessons(message: Message, db: Database):
    text, markup = lessons_view(db, message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(LessonCb.filter())
async def delete_lesson(callback: CallbackQuery, callback_data: LessonCb, db: Database):
    db.delete_lesson(callback.from_user.id, callback_data.id)
    text, markup = lessons_view(db, callback.from_user.id)
    await edit(callback, text, markup)
    await callback.answer("Удалено")
