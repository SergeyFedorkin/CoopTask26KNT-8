from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """edit_text, который не падает на «message is not modified»."""
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            raise
