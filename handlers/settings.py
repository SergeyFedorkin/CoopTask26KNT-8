from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from db import Database
from handlers.schedule import lessons_view
from handlers.tools import edit
from homework_logic import fmt_hours, parse_hours
from keyboards import BTN_SETTINGS, TEXT_INPUT, PickCb, SetCb, main_kb, pick_kb, settings_kb
import sheet
from ruz import Ruz, RuzError
from sheet import SheetError
from utils import fmt_num, now, parse_hhmm, q

router = Router()


class SetState(StatesGroup):
    group = State()
    summary_time = State()
    remind = State()


SOURCE_LABEL = {"group": "группа RUZ", "student": "личное RUZ", "sheet": "таблица факультета"}


def _settings_view(db: Database, uid: int):
    u = db.user(uid)
    kind = u["ruz_kind"]
    group = f"{q(u['ruz_label'])} ({SOURCE_LABEL.get(kind, kind)})" if kind else "не подключено"
    hours = parse_hours(u["remind_hours"])
    remind = ", ".join(fmt_hours(h) for h in hours) + " до срока" if hours else "выключены"
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"👥 Расписание: <b>{group}</b>\n"
        f"☀️ Утренняя сводка: <b>{u['summary_time']}</b>, {'вкл' if u['summary_on'] else 'выкл'}\n"
        f"🔔 Напоминания о дедлайнах: <b>{remind}</b>"
    )
    return text, settings_kb(bool(kind), bool(u["summary_on"]))


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def show_settings(message: Message, db: Database, state: FSMContext):
    await state.clear()
    text, markup = _settings_view(db, message.from_user.id)
    await message.answer(text, reply_markup=markup)


# ---------------- источник расписания: RUZ или таблица факультета ----------------
async def _connect_sheet(message: Message, db: Database, state: FSMContext, term: str, lead: str) -> bool:
    """Подключить группу из Google-таблицы факультета. True — получилось."""
    try:
        name = await sheet.find_group(term)
    except SheetError:
        return False
    if not name:
        return False
    db.update_user(message.from_user.id, ruz_kind="sheet", ruz_id=None, ruz_label=name)
    await state.clear()
    await message.answer(f"📋 {lead}: <b>{q(name)}</b>\nСмотри 📅 Сегодня или 🗓 Неделя.", reply_markup=main_kb)
    return True


async def _search_group(message: Message, db: Database, ruz: Ruz, state: FSMContext, term: str):
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        found = await ruz.search(term)
    except RuzError as e:
        lead = "RUZ сейчас недоступен, поэтому подключил расписание из таблицы факультета"
        if "@" not in term and await _connect_sheet(message, db, state, term, lead):
            return
        await state.clear()
        hint = "" if "@" in term else f"В таблице факультета группы «{q(term)}» тоже нет — проверь название.\n"
        return await message.answer(
            f"⚠️ RUZ не отвечает ({q(str(e))}).\n{hint}"
            "Можно добавить пары вручную: /addlesson", reply_markup=main_kb)
    if not found:
        lead = "В RUZ такой группы нет, зато она есть в таблице факультета — подключил"
        if "@" not in term and await _connect_sheet(message, db, state, term, lead):
            return
        await state.set_state(SetState.group)
        return await message.answer("Ничего не нашёл 🤷 Попробуй иначе (например, <code>БПИ251</code>) или /cancel")
    await state.set_state(SetState.group)
    await state.update_data(found=found)
    labels = [f"{f['label']} · {f['description']}"[:60] if f["description"] else f["label"] for f in found]
    await message.answer("Выбери:", reply_markup=pick_kb("group", labels, per_row=1))


@router.message(Command("group"))
async def group_cmd(message: Message, command: CommandObject, db: Database, ruz: Ruz, state: FSMContext):
    await state.clear()
    if command.args:
        return await _search_group(message, db, ruz, state, command.args.strip())
    await state.set_state(SetState.group)
    await message.answer("Напиши название группы (например, <code>БПИ251</code>)\n"
                         "или корпоративную почту <code>…@edu.hse.ru</code> — тогда будет личное расписание "
                         "со всеми английскими и майнорами.\n/cancel — отмена")


@router.callback_query(SetCb.filter(F.action == "group"))
async def group_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetState.group)
    await callback.message.answer("Напиши название группы (например, <code>БПИ251</code>) "
                                  "или почту <code>…@edu.hse.ru</code>.\n/cancel — отмена")
    await callback.answer()


@router.message(SetState.group, TEXT_INPUT)
async def group_typed(message: Message, db: Database, ruz: Ruz, state: FSMContext):
    await _search_group(message, db, ruz, state, message.text.strip())


@router.message(Command("sheet"))
async def sheet_cmd(message: Message, command: CommandObject, db: Database, state: FSMContext):
    await state.clear()
    if not command.args:
        return await message.answer("Формат: <code>/sheet 26КНТ-8</code> — расписание из Google-таблицы факультета "
                                    "(работает и вне сети ВШЭ)")
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        name = await sheet.find_group(command.args.strip())
    except SheetError as e:
        return await message.answer(f"⚠️ {q(str(e))}")
    if not name:
        return await message.answer("Такой группы в таблице нет. Проверь написание, например <code>26КНТ-8</code>")
    db.update_user(message.from_user.id, ruz_kind="sheet", ruz_id=None, ruz_label=name)
    await message.answer(f"📋 Подключил расписание из таблицы факультета: <b>{q(name)}</b>\n"
                         "Смотри 📅 Сегодня или 🗓 Неделя.", reply_markup=main_kb)


@router.callback_query(SetState.group, PickCb.filter(F.what == "group"))
async def group_picked(callback: CallbackQuery, callback_data: PickCb, db: Database, state: FSMContext):
    found = (await state.get_data()).get("found", [])
    if callback_data.i >= len(found):
        return await callback.answer("Кнопка устарела")
    g = found[callback_data.i]
    db.update_user(callback.from_user.id, ruz_kind=g["kind"], ruz_id=g["id"], ruz_label=g["label"])
    await state.clear()
    await edit(callback, f"✅ Подключил расписание: <b>{q(g['label'])}</b>\nСмотри 📅 Сегодня или 🗓 Неделя.")
    await callback.answer()


@router.callback_query(SetCb.filter(F.action == "ungroup"))
async def ungroup(callback: CallbackQuery, db: Database):
    db.update_user(callback.from_user.id, ruz_kind=None, ruz_id=None, ruz_label=None)
    await edit(callback, *_settings_view(db, callback.from_user.id))
    await callback.answer("Отвязал")


# ---------------- утренняя сводка ----------------
def _apply_summary_time(db: Database, uid: int, hhmm: str) -> None:
    # если время сегодня уже прошло — не шлём сводку прямо сейчас, начнём с завтра
    passed = now().strftime("%H:%M") >= hhmm
    fields = {"summary_time": hhmm, "summary_on": 1}
    if passed:
        fields["last_summary"] = now().date().isoformat()
    db.update_user(uid, **fields)


@router.message(Command("summary"))
async def summary_cmd(message: Message, command: CommandObject, db: Database):
    arg = (command.args or "").strip().lower()
    uid = message.from_user.id
    if arg in ("off", "выкл", "нет"):
        db.update_user(uid, summary_on=0)
        return await message.answer("🔕 Утренняя сводка выключена.")
    hhmm = parse_hhmm(arg)
    if not hhmm:
        return await message.answer("Формат: <code>/summary 07:30</code> или <code>/summary off</code>")
    _apply_summary_time(db, uid, hhmm)
    await message.answer(f"☀️ Буду присылать сводку в {hhmm}.")


@router.callback_query(SetCb.filter(F.action == "summary_time"))
async def summary_time_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetState.summary_time)
    await callback.message.answer("Во сколько присылать сводку? Например, <code>07:30</code>")
    await callback.answer()


@router.message(SetState.summary_time, TEXT_INPUT)
async def summary_time_typed(message: Message, db: Database, state: FSMContext):
    hhmm = parse_hhmm(message.text)
    if not hhmm:
        return await message.answer("Нужно время в формате ЧЧ:ММ, например <code>07:30</code>")
    _apply_summary_time(db, message.from_user.id, hhmm)
    await state.clear()
    text, markup = _settings_view(db, message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SetCb.filter(F.action == "summary_toggle"))
async def summary_toggle(callback: CallbackQuery, db: Database):
    u = db.user(callback.from_user.id)
    if u["summary_on"]:
        db.update_user(u["id"], summary_on=0)
    else:
        _apply_summary_time(db, u["id"], u["summary_time"])
    await edit(callback, *_settings_view(db, callback.from_user.id))
    await callback.answer()


# ---------------- напоминания ----------------
def _apply_remind(db: Database, uid: int, raw: str) -> str | None:
    if raw.lower() in ("off", "выкл", "нет", "0"):
        db.update_user(uid, remind_hours="")
        return "🔕 Напоминания о дедлайнах выключены."
    hours = parse_hours(raw)
    if not hours:
        return None
    db.update_user(uid, remind_hours=",".join(fmt_num(h) for h in hours))
    return "🔔 Буду напоминать " + ", ".join(fmt_hours(h) for h in hours) + " до дедлайна."


@router.message(Command("remind"))
async def remind_cmd(message: Message, command: CommandObject, db: Database):
    reply = _apply_remind(db, message.from_user.id, (command.args or "").strip())
    await message.answer(reply or "Формат: <code>/remind 24 3</code> (часы до дедлайна) или <code>/remind off</code>")


@router.callback_query(SetCb.filter(F.action == "remind"))
async def remind_btn(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetState.remind)
    await callback.message.answer("За сколько часов до дедлайна напоминать? Через пробел, например <code>48 24 3</code>.\n"
                                  "<code>off</code> — выключить.")
    await callback.answer()


@router.message(SetState.remind, TEXT_INPUT)
async def remind_typed(message: Message, db: Database, state: FSMContext):
    reply = _apply_remind(db, message.from_user.id, message.text.strip())
    if not reply:
        return await message.answer("Не понял. Пример: <code>24 3</code>")
    await state.clear()
    await message.answer(reply)


@router.callback_query(SetCb.filter(F.action == "lessons"))
async def lessons_btn(callback: CallbackQuery, db: Database):
    text, markup = lessons_view(db, callback.from_user.id)
    await callback.message.answer(text, reply_markup=markup)
    await callback.answer()
