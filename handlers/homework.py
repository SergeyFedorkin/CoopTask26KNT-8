import re
from datetime import datetime, time, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import TZ
from db import Database
from handlers.tools import edit
from homework_logic import fmt_hours, fmt_hw, mark_passed_reminders, parse_hours
from keyboards import BTN_ADD_HW, BTN_HW, TEXT_INPUT, HwCb, PickCb, hw_archive_kb, hw_list_kb, main_kb, pick_kb
from ruz import Ruz
from schedule_data import next_lesson_start, subject_candidates
from utils import fmt_dt, from_ts, match_name, now, parse_deadline, q

router = Router()
NEXT_LESSON_WORDS = {"пара", "к паре", "паре", "к следующей паре", "след пара"}
NO_DEADLINE_WORDS = {"без срока", "нет", "-", "—"}
LIST_LIMIT = 20


class AddHw(StatesGroup):
    subject = State()
    text = State()
    deadline = State()


def _canonical(subject: str, candidates: list[str]) -> str:
    found = match_name(subject, candidates)
    return found[0] if len(found) == 1 else subject


def _save(db: Database, uid: int, subject: str, text: str, deadline: datetime | None) -> str:
    ts = int(deadline.timestamp()) if deadline else None
    hw_id = db.add_hw(uid, subject, text, ts)
    mark_passed_reminders(db, uid, hw_id, ts)
    reply = "✅ Записал:\n" + fmt_hw(db.hw_get(uid, hw_id))
    if ts:
        all_hours = parse_hours(db.user(uid)["remind_hours"])
        upcoming = [h for h in all_hours if ts - h * 3600 > now().timestamp()]
        if upcoming:
            lines = [f"• {fmt_hours(h)} до срока — {fmt_dt(from_ts(ts - int(h * 3600)))}" for h in upcoming]
            reply += "\n\n🔔 Пришлю напоминания:\n" + "\n".join(lines)
        elif all_hours:
            reply += "\n\n🔔 До срока совсем мало времени, отдельного напоминания не будет."
    return reply
    
async def _start_add(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await message.bot.send_chat_action(message.chat.id, "typing")
    subjects = await subject_candidates(db, ruz, message.from_user.id)
    await state.set_state(AddHw.subject)
    await state.update_data(subjects=subjects)
    await message.answer(
        "📚 По какому предмету? Выбери или напиши название.\n(/cancel — отмена)",
        reply_markup=pick_kb("subject", subjects) if subjects else None,
    )


@router.message(Command("add"))
async def add_cmd(message: Message, command: CommandObject, db: Database, ruz: Ruz, state: FSMContext):
    await state.clear()
    if not command.args:
        return await _start_add(message, db, ruz, state)
        
    parts = [p.strip() for p in re.split(r"[;|]", command.args)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return await message.answer("Формат: <code>/add матан; №1.2–1.5; пт 18:00</code> (срок можно не писать)")
    uid = message.from_user.id
    subject = _canonical(parts[0], await subject_candidates(db, ruz, uid))
    deadline = None
    if len(parts) > 2 and parts[2]:
        raw = parts[2].lower()
        if raw in NEXT_LESSON_WORDS:
            deadline = await next_lesson_start(db, ruz, uid, subject)
            if not deadline:
                return await message.answer(f"Не нашёл ближайшую пару по «{q(subject)}» в расписании. Укажи дату.")
        elif raw not in NO_DEADLINE_WORDS:
            deadline = parse_deadline(raw)
            if not deadline:
                return await message.answer("Не понял срок. Примеры: <code>завтра</code>, <code>пт 18:00</code>, "
                                            "<code>25.10</code>, <code>+3</code>, <code>пара</code>")
    await message.answer(_save(db, uid, subject, parts[1], deadline))
    
@router.message(F.text == BTN_ADD_HW)
async def add_btn(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await state.clear()
    await _start_add(message, db, ruz, state)

async def _ask_text(message: Message, subject: str):
    await message.answer(f"📚 <b>{q(subject)}</b>\n\n✏️ Что задали?")

@router.callback_query(AddHw.subject, PickCb.filter(F.what == "subject"))
async def pick_subject(callback: CallbackQuery, callback_data: PickCb, state: FSMContext):
    subjects = (await state.get_data()).get("subjects", [])
    if callback_data.i >= len(subjects):
        return await callback.answer("Кнопка устарела, начни заново")
    subject = subjects[callback_data.i]
    await state.update_data(subject=subject)
    await state.set_state(AddHw.text)
    await edit(callback, f"📚 <b>{q(subject)}</b>\n\n✏️ Что задали?")
    await callback.answer()


@router.message(AddHw.subject, TEXT_INPUT)
async def type_subject(message: Message, state: FSMContext):
    subject = _canonical(message.text.strip()[:100], (await state.get_data()).get("subjects", []))
    await state.update_data(subject=subject)
    await state.set_state(AddHw.text)
    await _ask_text(message, subject)


@router.message(AddHw.text, TEXT_INPUT)
async def type_text(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await state.update_data(text=message.text.strip()[:1000])
    subject = (await state.get_data())["subject"]

    base = now()
    options: list[tuple[str, int | None]] = []
    nxt = await next_lesson_start(db, ruz, message.from_user.id, subject)
    if nxt:
        options.append((f"⏭ К следующей паре ({fmt_dt(nxt)})", int(nxt.timestamp())))
    for label, days in (("Завтра, 23:59", 1), ("Через неделю", 7)):
        dt = datetime.combine(base.date() + timedelta(days=days), time(23, 59), TZ)
        options.append((label, int(dt.timestamp())))
    options.append(("Без срока", None))

    await state.update_data(deadlines=[ts for _, ts in options])
    await state.set_state(AddHw.deadline)
    await message.answer(
        "⏰ Дедлайн? Выбери или напиши: <code>завтра</code>, <code>пт 18:00</code>, <code>25.10</code>, <code>+3</code>…",
        reply_markup=pick_kb("deadline", [label for label, _ in options], per_row=1),
    )


@router.callback_query(AddHw.deadline, PickCb.filter(F.what == "deadline"))
async def pick_deadline(callback: CallbackQuery, callback_data: PickCb, db: Database, state: FSMContext):
    data = await state.get_data()
    deadlines = data.get("deadlines", [])
    if callback_data.i >= len(deadlines):
        return await callback.answer("Кнопка устарела, начни заново")
    ts = deadlines[callback_data.i]
    await state.clear()
    await edit(callback, _save(db, callback.from_user.id, data["subject"], data["text"], from_ts(ts) if ts else None))
    await callback.answer()


@router.message(AddHw.deadline, TEXT_INPUT)
async def type_deadline(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    raw = message.text.strip().lower()
    data = await state.get_data()
    uid = message.from_user.id
    if raw in NO_DEADLINE_WORDS:
        deadline = None
    elif raw in NEXT_LESSON_WORDS:
        deadline = await next_lesson_start(db, ruz, uid, data["subject"])
        if not deadline:
            return await message.answer("Не нашёл ближайшую пару по этому предмету. Напиши дату.")
    else:
        deadline = parse_deadline(raw)
        if not deadline:
            return await message.answer("Не понял 🤔 Примеры: <code>завтра</code>, <code>пт 18:00</code>, "
                                        "<code>25.10 23:59</code>, <code>+3</code>, <code>без срока</code>")
    await state.clear()
    await message.answer(_save(db, uid, data["subject"], data["text"], deadline), reply_markup=main_kb)

def _render_active(db: Database, uid: int, delete_mode: bool = False):
    rows = db.hw_active(uid)
    if not rows:
        return "📝 Домашки нет — красота 😎\nДобавить: ➕ или /add", hw_list_kb([])
    shown = rows[:LIST_LIMIT]
    lines = [f"📝 <b>Домашка</b> ({len(rows)})", ""]
    lines += [fmt_hw(h, n) for n, h in enumerate(shown, 1)]
    if len(rows) > LIST_LIMIT:
        lines.append(f"\n…и ещё {len(rows) - LIST_LIMIT}")
    lines.append("\n" + ("Нажми 🗑 с номером, чтобы удалить." if delete_mode else "Сделал — жми ✅ с номером."))
    return "\n".join(lines), hw_list_kb([h["id"] for h in shown], delete_mode)


def _render_archive(db: Database, uid: int):
    rows = db.hw_done_list(uid)
    if not rows:
        return "🗂 Выполненных пока нет.", hw_archive_kb([])
    lines = ["🗂 <b>Выполненные</b> (последние 15)", ""]
    for n, h in enumerate(rows, 1):
        lines.append(f"{n}. <s>{q(h['subject'])} — {q(h['text'])}</s>  ✅ {from_ts(h['done_at']):%d.%m}")
    lines.append("\n↩️ — вернуть в активные")
    return "\n".join(lines), hw_archive_kb([h["id"] for h in rows])


@router.message(Command("hw"))
@router.message(F.text == BTN_HW)
async def show_hw(message: Message, db: Database, state: FSMContext):
    await state.clear()
    text, markup = _render_active(db, message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(HwCb.filter(F.action == "done"))
async def hw_done(callback: CallbackQuery, callback_data: HwCb, db: Database):
    db.hw_set_done(callback.from_user.id, callback_data.id, True)
    await edit(callback, *_render_active(db, callback.from_user.id))
    await callback.answer("✅ Красавчик!")


@router.callback_query(HwCb.filter(F.action == "rdone"))
async def hw_done_from_reminder(callback: CallbackQuery, callback_data: HwCb, db: Database):
    db.hw_set_done(callback.from_user.id, callback_data.id, True)
    await edit(callback, callback.message.html_text + "\n\n✅ <b>Сделано</b>")
    await callback.answer("✅ Красавчик!")


@router.callback_query(HwCb.filter(F.action == "list"))
async def hw_list(callback: CallbackQuery, db: Database):
    await edit(callback, *_render_active(db, callback.from_user.id))
    await callback.answer()


@router.callback_query(HwCb.filter(F.action == "delmode"))
async def hw_delmode(callback: CallbackQuery, db: Database):
    await edit(callback, *_render_active(db, callback.from_user.id, delete_mode=True))
    await callback.answer()


@router.callback_query(HwCb.filter(F.action == "del"))
async def hw_delete(callback: CallbackQuery, callback_data: HwCb, db: Database):
    db.hw_delete(callback.from_user.id, callback_data.id)
    await edit(callback, *_render_active(db, callback.from_user.id, delete_mode=True))
    await callback.answer("🗑 Удалено")


@router.callback_query(HwCb.filter(F.action == "archive"))
async def hw_archive(callback: CallbackQuery, db: Database):
    await edit(callback, *_render_archive(db, callback.from_user.id))
    await callback.answer()


@router.callback_query(HwCb.filter(F.action == "undo"))
async def hw_undo(callback: CallbackQuery, callback_data: HwCb, db: Database):
    db.hw_set_done(callback.from_user.id, callback_data.id, False)
    await edit(callback, *_render_archive(db, callback.from_user.id))
    await callback.answer("↩️ Вернул в активные")
