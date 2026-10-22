"""Фоновый цикл: напоминания о дедлайнах и утренняя сводка."""
import asyncio
import logging
import time
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from db import Database
from homework_logic import fmt_hw, parse_hours
from keyboards import done_kb
from ruz import Ruz
from summary import summary_text
from utils import at, now

log = logging.getLogger(__name__)
TICK_SECONDS = 30
SUMMARY_WINDOW = timedelta(hours=2)   # если бот был выключен в момент сводки — догоним в течение 2 ч


async def _send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramAPIError as e:
        log.warning("Не удалось отправить %s: %s", chat_id, e)
        return False


async def check_reminders(bot: Bot, db: Database) -> None:
    ts = int(time.time())
    users = {u["id"]: parse_hours(u["remind_hours"]) for u in db.users()}
    for hw in db.hw_pending_all(ts):
        hours = users.get(hw["user_id"], [])
        sent = db.reminders_sent(hw["id"])
        due = [h for h in hours if h not in sent and hw["deadline"] - h * 3600 <= ts]
        if not due:
            continue
        # шлём одно сообщение, даже если «созрело» сразу несколько порогов
        if await _send(bot, hw["user_id"], "⏰ <b>Напоминание о дедлайне</b>\n\n" + fmt_hw(hw),
                       reply_markup=done_kb(hw["id"])):
            db.mark_reminders(hw["id"], due)


async def check_summaries(bot: Bot, db: Database, ruz: Ruz) -> None:
    cur = now()
    day = cur.date().isoformat()
    for u in db.users():
        if not u["summary_on"] or u["last_summary"] == day:
            continue
        planned = at(cur.date(), u["summary_time"])
        if not planned <= cur < planned + SUMMARY_WINDOW:
            continue
        db.update_user(u["id"], last_summary=day)   # сначала отмечаем, чтобы не задублировать
        await _send(bot, u["id"], await summary_text(db, ruz, u["id"]))


async def run(bot: Bot, db: Database, ruz: Ruz) -> None:
    log.info("Планировщик запущен")
    while True:
        try:
            await check_reminders(bot, db)
            await check_summaries(bot, db, ruz)
        except Exception:
            log.exception("Ошибка в планировщике")
        await asyncio.sleep(TICK_SECONDS)
