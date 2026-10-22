import re
import time
from sqlite3 import Row

from db import Database
from utils import fmt_dt, fmt_left, fmt_num, from_ts, q


def hw_mark(h: Row) -> str:
    if not h["deadline"]:
        return "⚪️"
    left = h["deadline"] - time.time()
    if left < 0:
        return "🔴"
    if left < 86400:
        return "🟠"
    if left < 3 * 86400:
        return "🟡"
    return "🟢"


def fmt_hw(h: Row, n: int | None = None) -> str:
    num = f"{n}. " if n is not None else ""
    line = f"{hw_mark(h)} {num}<b>{q(h['subject'])}</b> — {q(h['text'])}"
    if h["deadline"]:
        dt = from_ts(h["deadline"])
        line += f"\n      ⏰ {fmt_dt(dt)} · {fmt_left(dt)}"
    return line


def mark_passed_reminders(db: Database, uid: int, hw_id: int, deadline: int | None) -> None:
    if not deadline:
        return
    hours = parse_hours(db.user(uid)["remind_hours"])
    passed = [h for h in hours if deadline - h * 3600 <= time.time()]
    if passed:
        db.mark_reminders(hw_id, passed)


def parse_hours(text: str) -> list[float]:
    result = []
    for part in re.split(r"[,\s]+", text.strip()):
        try:
            v = float(part.replace("ч", "").replace(",", "."))
        except ValueError:
            continue
        if 0 < v <= 24 * 14:
            result.append(v)
    return sorted(set(result), reverse=True)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def fmt_hours(h: float) -> str:
    if h < 1:
        return f"за {round(h * 60)} мин"
    if h % 24 == 0:
        days = int(h // 24)
        return "за сутки" if days == 1 else f"за {days} {plural(days, 'день', 'дня', 'дней')}"
    return f"за {fmt_num(h)} ч"
