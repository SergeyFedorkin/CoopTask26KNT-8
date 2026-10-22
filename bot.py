import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import scheduler
from config import settings
from db import Database
from handlers import common, grades, homework, schedule
from handlers import settings as settings_handlers
from ruz import Ruz

COMMANDS = [
    BotCommand(command="today", description="Пары сегодня"),
    BotCommand(command="tomorrow", description="Пары завтра"),
    BotCommand(command="week", description="Расписание на неделю"),
    BotCommand(command="hw", description="Список ДЗ"),
    BotCommand(command="add", description="Добавить ДЗ"),
    BotCommand(command="grades", description="Оценки и накоп"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="help", description="Все команды"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.token:
        sys.exit("Нет BOT_TOKEN. Создай файл .env рядом с bot.py (см. .env.example)")

    session = AiohttpSession(proxy=settings.tg_proxy) if settings.tg_proxy else None
    bot = Bot(
        settings.token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    db = Database(settings.db_path)
    ruz = Ruz(settings.ruz_proxy, settings.ruz_verify_ssl)
    await ruz.start()

    # db и ruz автоматически попадают в хендлеры по имени аргумента
    dp = Dispatcher(storage=MemoryStorage(), db=db, ruz=ruz)
    if settings.allowed_users:
        dp.message.filter(F.from_user.id.in_(settings.allowed_users))
        dp.callback_query.filter(F.from_user.id.in_(settings.allowed_users))
    dp.include_routers(
        common.router, schedule.router, homework.router, grades.router, settings_handlers.router,
        common.fallback,   # «не понял» — строго последним
    )

    background = asyncio.create_task(scheduler.run(bot, db, ruz))
    try:
        try:
            await bot.set_my_commands(COMMANDS)
        except TelegramNetworkError as e:
            logging.warning("Не удалось выставить меню команд (сеть): %s", e)
        await dp.start_polling(bot)
    finally:
        background.cancel()
        await ruz.close()
        db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
