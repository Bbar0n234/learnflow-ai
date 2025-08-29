"""Handlers for authentication-related commands."""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
import telegramify_markdown

from ..database import AuthDatabase
from ..settings import get_settings

logger = logging.getLogger(__name__)

router = Router()
settings = get_settings()

# Initialize auth database
auth_db = AuthDatabase(settings.database_url or "")


@router.message(Command("web_auth"))
async def web_auth_command(message: Message):
    """Generate authentication code for web UI access."""
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    if not settings.database_url:
        await message.answer(
            telegramify_markdown.markdownify(
                "⚠️ Аутентификация для веб-интерфейса временно недоступна.\n"
                "Администратор не настроил подключение к базе данных."
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    try:
        # Make sure database is connected
        if not auth_db.pool:
            await auth_db.connect()
        
        # Generate auth code
        code = await auth_db.create_auth_code(username, user_id)
        
        # Send code to user with instructions
        auth_text = (
            "🔐 *Код авторизации для веб-интерфейса*\n\n"
            f"Ваш код: `{code}`\n"
            f"Имя пользователя: `{username}`\n\n"
            "📝 *Инструкция:*\n"
            "1. Откройте веб-интерфейс LearnFlow AI\n"
            "2. Нажмите кнопку 'Войти'\n"
            f"3. Введите имя пользователя: {username}\n"
            f"4. Введите код: {code}\n\n"
            "⏱ Код действителен 5 минут.\n"
            "После входа вы получите доступ к своим материалам."
        )
        
        await message.answer(
            telegramify_markdown.markdownify(auth_text),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        logger.info(f"Generated auth code for user {username} (ID: {user_id})")
        
    except Exception as e:
        logger.error(f"Failed to generate auth code for user {user_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify(
                "❌ Ошибка при создании кода авторизации.\n"
                "Попробуйте еще раз через несколько секунд."
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )