"""
Telegram бот для взаимодействия с системой подготовки экзаменационных материалов.
Обязательный компонент согласно плану - основной пользовательский интерфейс.
"""

import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.enums import ChatAction, ParseMode
import telegramify_markdown

from .settings import get_settings


# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)



# Создаем роутер для обработчиков
router = Router()


class LearnFlowBot:
    """Telegram бот для LearnFlow AI системы"""
    
    def __init__(self, bot: Bot):
        self.settings = get_settings()
        self.api_base_url = f"http://{self.settings.api.learnflow_host}:{self.settings.api.learnflow_port}"
        self.bot = bot


# Создаем глобальный экземпляр бота
bot_instance: Optional[LearnFlowBot] = None


@router.message(CommandStart())
async def start_command(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    welcome_text = (
        "🎓 Добро пожаловать в LearnFlow AI!\n\n"
        "Я помогу вам подготовить материалы для экзаменов.\n\n"
        "📝 Просто отправьте мне экзаменационный вопрос, и я:\n"
        "• Создам обучающий материал\n"
        "• Сгенерирую дополнительные вопросы\n"
        "• Подготовлю подробные ответы\n\n"
        "Начните с отправки вопроса!"
    )
    
    await message.answer(
        telegramify_markdown.markdownify(welcome_text),
        parse_mode=ParseMode.MARKDOWN_V2
    )


@router.message(Command("help"))
async def help_command(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "🔧 *Команды бота:*\n\n"
        "/start - Начать работу\n"
        "/help - Показать помощь\n"
        "/reset - Начать новую сессию\n"
        "/status - Показать статус текущей сессии\n\n"
        "📋 *Как использовать:*\n"
        "1. Отправьте экзаменационный вопрос\n"
        "2. Дождитесь генерации материала и вопросов\n"
        "3. Оцените предложенные вопросы\n"
        "4. Получите готовые материалы\n\n"
        "💡 *Совет:* Чем подробнее вопрос, тем лучше результат!"
    )
    
    await message.answer(
        telegramify_markdown.markdownify(help_text),
        parse_mode=ParseMode.MARKDOWN_V2
    )


@router.message(Command("reset"))
async def reset_command(message: Message):
    """Обработчик команды /reset"""
    user_id = message.from_user.id
    thread_id = str(user_id)
    
    try:
        await bot_instance._delete_thread(thread_id)
        logger.info(f"Deleted thread {thread_id} for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to delete thread {thread_id}: {e}")
    
    await message.answer(
        telegramify_markdown.markdownify("🔄 Сессия сброшена! Можете начать с нового вопроса."),
        parse_mode=ParseMode.MARKDOWN_V2
    )


@router.message(Command("status"))
async def status_command(message: Message):
    """Обработчик команды /status"""
    user_id = message.from_user.id
    thread_id = str(user_id)
    
    try:
        status_info = await bot_instance._get_thread_status(thread_id)
        description = status_info['current_step']['description']
        
        status_text = (
            f"📊 *Статус сессии:*\n\n"
            f"📍 {description}\n\n"
        )
        
        await message.answer(
            telegramify_markdown.markdownify(status_text),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error getting status for user {user_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify("❌ Ошибка получения статуса. Попробуйте /reset."),
            parse_mode=ParseMode.MARKDOWN_V2
        )


@router.message(F.text)
async def handle_message(message: Message):
    """Обработчик текстовых сообщений"""
    user_id = message.from_user.id
    message_text = message.text
    
    # Показываем индикатор печати
    await message.bot.send_chat_action(
        chat_id=message.chat.id, 
        action=ChatAction.TYPING
    )
    
    try:
        # Используем user_id как thread_id
        thread_id = str(user_id)
        
        # Отправляем запрос в LearnFlow API
        result = await bot_instance._process_message(thread_id, message_text)
        
        # Обрабатываем ответ
        await _handle_api_response(message, result)
        
    except Exception as e:
        logger.error(f"Error processing message from user {user_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify("❌ Произошла ошибка при обработке. Попробуйте еще раз или используйте /reset."),
            parse_mode=ParseMode.MARKDOWN_V2
        )


async def _handle_api_response(message: Message, result: Dict[str, Any]):
    """Обработка ответа от API"""
    result_data = result.get("result", [])
    
    if isinstance(result_data, list):
        # HITL взаимодействие - отправляем вопросы пользователю
        for msg in result_data:
            # Разбиваем длинные сообщения
            if len(msg) > 4000:
                # Отправляем по частям
                chunks = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
                for chunk in chunks:
                    await message.answer(
                        telegramify_markdown.markdownify(chunk),
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            else:
                await message.answer(
                    telegramify_markdown.markdownify(msg),
                    parse_mode=ParseMode.MARKDOWN_V2
                )


async def main():
    """Запуск бота"""
    global bot_instance
    
    settings = get_settings()
    
    # Создание бота и диспетчера
    bot = Bot(token=settings.telegram.token)
    dp = Dispatcher()
    
    # Инициализация бота
    bot_instance = LearnFlowBot(bot)
    
    # Регистрация роутера
    dp.include_router(router)
    
    # Запуск бота
    logger.info("Starting LearnFlow Telegram Bot...")
    await dp.start_polling(bot)


# Методы для работы с API (добавляем в класс LearnFlowBot)
async def _process_message(self, thread_id: str, message: str) -> Dict[str, Any]:
    """Отправка сообщения в LearnFlow API"""
    async with aiohttp.ClientSession() as session:
        payload = {
            "thread_id": thread_id,
            "message": message
        }
        
        async with session.post(
            f"{self.api_base_url}/process",
            json=payload
        ) as response:
            if response.status != 200:
                raise Exception(f"API error: {response.status}")
            
            return await response.json()


async def _get_thread_status(self, thread_id: str) -> Dict[str, Any]:
    """Получение статуса thread'а"""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{self.api_base_url}/state/{thread_id}"
        ) as response:
            if response.status != 200:
                raise Exception(f"API error: {response.status}")
            
            return await response.json()


async def _delete_thread(self, thread_id: str):
    """Удаление thread'а"""
    async with aiohttp.ClientSession() as session:
        async with session.delete(
            f"{self.api_base_url}/thread/{thread_id}"
        ) as response:
            if response.status != 200:
                raise Exception(f"API error: {response.status}")


# Добавляем методы в класс LearnFlowBot
LearnFlowBot._process_message = _process_message
LearnFlowBot._get_thread_status = _get_thread_status
LearnFlowBot._delete_thread = _delete_thread


if __name__ == "__main__":
    asyncio.run(main()) 