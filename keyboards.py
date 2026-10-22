from aiogram import F
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "📆 Завтра"
BTN_WEEK = "🗓 Неделя"
BTN_HW = "📝 ДЗ"
BTN_ADD_HW = "➕ Добавить ДЗ"
BTN_GRADES = "📊 Оценки"
BTN_SETTINGS = "⚙️ Настройки"
MENU_BUTTONS = {BTN_TODAY, BTN_TOMORROW, BTN_WEEK, BTN_HW, BTN_ADD_HW, BTN_GRADES, BTN_SETTINGS}
# фильтр для ввода в FSM: обычный текст, не команда и не кнопка меню
TEXT_INPUT = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS)

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW), KeyboardButton(text=BTN_WEEK)],
        [KeyboardButton(text=BTN_HW), KeyboardButton(text=BTN_ADD_HW)],
        [KeyboardButton(text=BTN_GRADES), KeyboardButton(text=BTN_SETTINGS)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


class DayCb(CallbackData, prefix="day"):
    d: str            # YYYY-MM-DD


class WeekCb(CallbackData, prefix="wk"):
    d: str            # понедельник недели


class HwCb(CallbackData, prefix="hw"):
    action: str       # done | rdone | undo | del | list | archive | delmode
    id: int = 0


class PickCb(CallbackData, prefix="pick"):
    what: str         # subject | deadline | group
    i: int


class SetCb(CallbackData, prefix="set"):
    action: str


class LessonCb(CallbackData, prefix="les"):
    id: int


def btn(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def day_nav(prev_d: str, next_d: str, today_d: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        btn("◀️", DayCb(d=prev_d)), btn("Сегодня", DayCb(d=today_d)), btn("▶️", DayCb(d=next_d)),
    ]])


def week_nav(prev_d: str, next_d: str, cur_d: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        btn("◀️ пред.", WeekCb(d=prev_d)), btn("Текущая", WeekCb(d=cur_d)), btn("след. ▶️", WeekCb(d=next_d)),
    ]])


def hw_list_kb(ids: list[int], delete_mode: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n, hw_id in enumerate(ids, 1):
        if delete_mode:
            kb.add(btn(f"🗑 {n}", HwCb(action="del", id=hw_id)))
        else:
            kb.add(btn(f"✅ {n}", HwCb(action="done", id=hw_id)))
    kb.adjust(5)
    bottom = [btn("🗂 Выполненные", HwCb(action="archive"))]
    if ids:
        bottom.append(btn("⬅️ Назад", HwCb(action="list")) if delete_mode else btn("🗑 Удалить…", HwCb(action="delmode")))
    kb.row(*bottom)
    return kb.as_markup()


def hw_archive_kb(ids: list[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for n, hw_id in enumerate(ids, 1):
        kb.add(btn(f"↩️ {n}", HwCb(action="undo", id=hw_id)))
    kb.adjust(5)
    kb.row(btn("⬅️ К активным", HwCb(action="list")))
    return kb.as_markup()


def pick_kb(what: str, labels: list[str], per_row: int = 2) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i, label in enumerate(labels):
        kb.add(btn(label[:60], PickCb(what=what, i=i)))
    kb.adjust(per_row)
    return kb.as_markup()


def settings_kb(has_group: bool, summary_on: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("👥 Группа RUZ", SetCb(action="group")))
    if has_group:
        kb.add(btn("✖️ Отвязать", SetCb(action="ungroup")))
    kb.row(btn("⏰ Время сводки", SetCb(action="summary_time")),
           btn("🔕 Выкл сводку" if summary_on else "🔔 Вкл сводку", SetCb(action="summary_toggle")))
    kb.row(btn("🔔 Напоминания о дедлайнах", SetCb(action="remind")))
    kb.row(btn("✍️ Мои ручные пары", SetCb(action="lessons")))
    return kb.as_markup()


def done_kb(hw_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[btn("✅ Сделано", HwCb(action="rdone", id=hw_id))]])
