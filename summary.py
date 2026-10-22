"""Утренняя сводка."""
import time
from datetime import timedelta

from db import Database
from homework_logic import fmt_hw
from ruz import Ruz
from schedule_texts import day_text
from utils import from_ts, today


async def summary_text(db: Database, ruz: Ruz, uid: int) -> str:
    d = today()
    parts = ["☀️ <b>Доброе утро!</b>\n", await day_text(db, ruz, uid, d)]
    active = db.hw_active(uid)
    overdue = [h for h in active if h["deadline"] and h["deadline"] < time.time()]
    tomorrow = [h for h in active if h["deadline"] and from_ts(h["deadline"]).date() == d + timedelta(days=1)]
    if overdue:
        parts.append("\n🔴 <b>Просрочено:</b>\n" + "\n".join(fmt_hw(h) for h in overdue))
    if tomorrow:
        parts.append("\n🟠 <b>Завтра сдать:</b>\n" + "\n".join(fmt_hw(h) for h in tomorrow))
    rest = len(active) - len(overdue) - len(tomorrow) - sum(
        1 for h in active if h["deadline"] and from_ts(h["deadline"]).date() == d)
    if rest > 0:
        parts.append(f"\nЕщё в списке: {rest} — /hw")
    return "\n".join(parts)
