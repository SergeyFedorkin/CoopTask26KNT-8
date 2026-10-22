"""Тексты расписания: день и неделя."""
from datetime import date, timedelta
from html import escape

from db import Database
from homework_logic import fmt_hw
from ruz import Lesson, Ruz
from schedule_data import get_lessons
from utils import MONTHS, WD_SHORT, at, fmt_day, from_ts, q, today


def fmt_lesson(lesson: Lesson) -> str:
    line = f"{'✍️' if lesson.manual else '▫️'} <b>{lesson.begin}–{lesson.end}</b>  {q(lesson.title)}"
    if lesson.kind:
        line += f" <i>({q(lesson.kind.lower())})</i>"
    extra = []
    if lesson.room:
        extra.append(f"📍 {q(lesson.room)}")
    if lesson.lecturer:
        extra.append(f"👤 {q(lesson.lecturer)}")
    if lesson.url:
        extra.append(f'<a href="{escape(lesson.url)}">🔗 онлайн</a>')
    if extra:
        line += "\n      " + " · ".join(extra)
    return line


async def day_text(db: Database, ruz: Ruz, uid: int, d: date) -> str:
    lessons, warning = await get_lessons(db, ruz, uid, d, d)
    title = f"📅 <b>{fmt_day(d)}</b>" + (" · сегодня" if d == today() else "")
    lines = [title, ""]
    if lessons[d]:
        lines += [fmt_lesson(lesson) for lesson in lessons[d]]
    elif db.user(uid)["ruz_kind"] or db.lessons_all(uid):
        lines.append("Пар нет 🎉")
    else:
        lines.append("Расписание не подключено. ⚙️ Настройки → «Группа RUZ» или /addlesson")

    due = [h for h in db.hw_active(uid) if h["deadline"] and from_ts(h["deadline"]).date() == d]
    if due:
        lines += ["", "📝 <b>Сдать в этот день:</b>"] + [fmt_hw(h) for h in due]
    if warning:
        lines += ["", warning]
    return "\n".join(lines)


async def week_text(db: Database, ruz: Ruz, uid: int, monday: date) -> str:
    sunday = monday + timedelta(days=6)
    lessons, warning = await get_lessons(db, ruz, uid, monday, sunday)
    lines = [f"🗓 <b>{monday.day} {MONTHS[monday.month - 1]} – {sunday.day} {MONTHS[sunday.month - 1]}</b>"]
    for d in sorted(lessons):
        if not lessons[d]:
            continue
        mark = "  ← сегодня" if d == today() else ""
        lines.append(f"\n<b>{WD_SHORT[d.weekday()].upper()}, {d.day:02d}.{d.month:02d}</b>{mark}")
        for lesson in lessons[d]:
            room = f" · {q(lesson.room)}" if lesson.room else ""
            lines.append(f"{'✍️ ' if lesson.manual else ''}{lesson.begin}–{lesson.end}  {q(lesson.title)}{room}")
    if len(lines) == 1:
        lines.append("\nПар на этой неделе нет.")

    start_ts = int(at(monday, "00:00").timestamp())
    end_ts = int(at(sunday, "23:59").timestamp()) + 60
    due = [h for h in db.hw_active(uid) if h["deadline"] and start_ts <= h["deadline"] < end_ts]
    if due:
        lines += ["", "📝 <b>Дедлайны на неделе:</b>"] + [fmt_hw(h) for h in due]
    if warning:
        lines += ["", warning]
    return "\n".join(lines)
