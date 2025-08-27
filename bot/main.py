"""
Telegram бот для взаимодействия с системой подготовки экзаменационных материалов.
Обязательный компонент согласно плану - основной пользовательский интерфейс.
Поддерживает обработку текста и изображений конспектов.
"""

import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, PhotoSize
from aiogram.filters import Command, CommandStart
from aiogram.enums import ChatAction, ParseMode
import telegramify_markdown  # type: ignore[import-untyped]

from .settings import get_settings
from .handlers.hitl_settings import router as hitl_router
from .handlers.prompt_config import router as prompt_config_router
from .handlers.export_handlers import router as export_router

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Настройка логирования с файлом и консолью
handlers = [
    logging.StreamHandler(),  # Console output
    logging.FileHandler(log_dir / "bot.log", encoding="utf-8")  # File output
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=handlers
)
logger = logging.getLogger(__name__)


# Создаем роутер для обработчиков
router = Router()


class LearnFlowBot:
    """Telegram бот для LearnFlow AI системы"""

    def __init__(self, bot: Bot):
        self.settings = get_settings()
        self.api_base_url = f"http://{self.settings.api.host}:{self.settings.api.port}"
        self.bot = bot

        # Хранилище для группировки медиа (photo + text)
        self.pending_media: Dict[int, Dict[str, Any]] = {}

    async def _process_message(
        self, thread_id: str, message_text: str, image_paths: list[str] = None
    ) -> Dict[str, Any]:
        """Унифицированный метод отправки сообщения в API"""
        request_data = {
            "message": message_text,
            "thread_id": thread_id
        }
        
        # Добавляем изображения если они есть
        if image_paths:
            request_data["image_paths"] = image_paths
            
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_base_url}/process",
                json=request_data,
            ) as response:
                if response.status != 200:
                    raise Exception(f"API error: {response.status}")
                return await response.json()

    async def _download_photo(self, photo: PhotoSize) -> bytes:
        """Скачивание фото через Telegram API"""
        file = await self.bot.get_file(photo.file_id)
        if not file.file_path:
            raise Exception("File path is None")
        photo_data = await self.bot.download_file(file.file_path)
        if not photo_data:
            raise Exception("Failed to download photo data")
        return photo_data.read()

    async def _upload_images(
        self, thread_id: str, image_data_list: list[bytes]
    ) -> list[str]:
        """Загрузка изображений в API"""
        image_paths = []
        async with aiohttp.ClientSession() as session:
            for i, image_data in enumerate(image_data_list):
                data = aiohttp.FormData()
                data.add_field(
                    "file",
                    image_data,
                    filename=f"image_{i}.jpg",
                    content_type="image/jpeg",
                )
                data.add_field("thread_id", thread_id)

                async with session.post(
                    f"{self.api_base_url}/upload_image", data=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        image_paths.append(result.get("file_path", ""))
                    else:
                        logger.error(f"Failed to upload image {i}: {response.status}")
        return image_paths

    async def _get_thread_status(self, thread_id: str) -> Dict[str, Any]:
        """Получение статуса thread'а"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_base_url}/state/{thread_id}"
            ) as response:
                if response.status != 200:
                    raise Exception(f"API error: {response.status}")
                return await response.json()

    async def _delete_thread(self, thread_id: str) -> Dict[str, Any]:
        """Удаление thread'а"""
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.api_base_url}/state/{thread_id}"
            ) as response:
                if response.status != 200:
                    raise Exception(f"API error: {response.status}")
                return await response.json()


# Создаем глобальный экземпляр бота
bot_instance: Optional[LearnFlowBot] = None


@router.message(CommandStart())
async def start_command(message: Message):
    """Обработчик команды /start"""
    welcome_text = (
        "🎓 Добро пожаловать в LearnFlow AI!\n\n"
        "Я помогу вам подготовить материалы для экзаменов.\n\n"
        "📝 Вы можете отправить мне:\n"
        "• Текстовый экзаменационный вопрос\n"
        "• Вопрос с фотографиями ваших конспектов\n"
        "• Просто фотографии конспектов (я помогу их обработать)\n\n"
        "🔧 Я создам:\n"
        "• Обучающий материал\n"
        "• Дополнительные вопросы для самопроверки\n"
        "• Подробные ответы\n\n"
        "📸 *Совет:* Отправляйте фото конспектов для более точных материалов!\n\n"
        "Начните с отправки вопроса или фотографий!"
    )

    await message.answer(
        telegramify_markdown.markdownify(welcome_text), parse_mode=ParseMode.MARKDOWN_V2
    )


@router.message(Command("help"))
async def help_command(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "🔧 *Команды бота:*\n\n"
        "/start - Начать работу\n"
        "/help - Показать помощь\n"
        "/hitl - Настройки обработки (автономный/управляемый)\n"
        "/configure - Настройка промптов и персонализация\n"
        "/reset_prompts - Сбросить промпты к дефолтным\n"
        "/reset - Начать новую сессию\n"
        "/status - Показать статус текущей сессии\n\n"
        "📤 *Экспорт документов:*\n"
        "/export - Быстрый экспорт текущей сессии\n"
        "/export_menu - Выбор параметров экспорта\n"
        "/sessions - История последних сессий\n"
        "/export_settings - Настройки экспорта\n\n"
        "📋 *Как использовать:*\n"
        "1. Отправьте экзаменационный вопрос\n"
        "2. Можете добавить фото ваших конспектов\n"
        "3. Дождитесь генерации материала и вопросов\n"
        "4. Оцените предложенные вопросы\n"
        "5. Получите готовые материалы\n"
        "6. Экспортируйте в Markdown или PDF\n\n"
        "📸 *Работа с изображениями:*\n"
        "• Отправьте до 10 фотографий конспектов\n"
        "• Фото будут распознаны и использованы в материале\n"
        "• Поддерживаются форматы: JPG, PNG\n"
        "• Максимальный размер: 10 МБ на фото\n\n"
        "💡 *Совет:* Чем четче фото и подробнее вопрос, тем лучше результат!"
    )

    await message.answer(
        telegramify_markdown.markdownify(help_text), parse_mode=ParseMode.MARKDOWN_V2
    )


@router.message(Command("reset"))
async def reset_command(message: Message):
    """Обработчик команды /reset"""
    if not message.from_user:
        return
    user_id = message.from_user.id
    thread_id = str(user_id)

    if not bot_instance:
        return

    try:
        await bot_instance._delete_thread(thread_id)
        # Очищаем pending media для пользователя
        if user_id in bot_instance.pending_media:
            del bot_instance.pending_media[user_id]
        logger.info(f"Deleted thread {thread_id} for user {user_id}")

        await message.answer(
            telegramify_markdown.markdownify(
                "🔄 Сессия сброшена! Можете начать с нового вопроса."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception as e:
        logger.warning(f"Failed to delete thread {thread_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify(
                "❌ Ошибка при сбросе сессии. Попробуйте еще раз."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


@router.message(Command("status"))
async def status_command(message: Message):
    """Обработчик команды /status"""
    if not message.from_user:
        return
    user_id = message.from_user.id
    thread_id = str(user_id)

    if not bot_instance:
        return

    try:
        status_info = await bot_instance._get_thread_status(thread_id)
        description = status_info["current_step"]["description"]

        status_text = f"📊 *Статус сессии:*\n\n📍 {description}\n\n"

        await message.answer(
            telegramify_markdown.markdownify(status_text),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    except Exception as e:
        logger.error(f"Error getting status for user {user_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify(
                "❌ Ошибка получения статуса. Попробуйте /reset."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


@router.message(F.photo)
async def handle_photo(message: Message):
    """Обработчик фото сообщений"""
    if not message.from_user or not message.bot:
        return
    user_id = message.from_user.id

    try:
        # Показываем индикатор загрузки
        await message.bot.send_chat_action(
            chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO
        )

        # Получаем фото наибольшего размера
        if not message.photo:
            return
        photo = message.photo[-1]  # Последнее фото имеет наибольший размер

        # Скачиваем фото
        if not bot_instance:
            return
        photo_data = await bot_instance._download_photo(photo)

        # Инициализируем pending media для пользователя если нужно
        if user_id not in bot_instance.pending_media:
            bot_instance.pending_media[user_id] = {
                "photos": [],
                "text": None,
                "timestamp": message.date,
            }

        # Добавляем фото в pending media
        bot_instance.pending_media[user_id]["photos"].append(photo_data)

        # Если есть подпись к фото, используем её как текст
        if message.caption:
            bot_instance.pending_media[user_id]["text"] = message.caption

        photo_count = len(bot_instance.pending_media[user_id]["photos"])

        # Отправляем подтверждение
        confirmation_text = (
            f"📸 Получена фотография {photo_count}/10\n\n"
            "Отправьте еще фото или текст с экзаменационным вопросом для начала обработки.\n"
            "Или просто отправьте любое сообщение для обработки всех загруженных фотографий."
        )

        await message.answer(
            telegramify_markdown.markdownify(confirmation_text),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    except Exception as e:
        logger.error(f"Error handling photo from user {user_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify(
                "❌ Ошибка при обработке фотографии. Попробуйте еще раз."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(message: Message):
    """Обработчик текстовых сообщений"""
    if not message.from_user or not message.bot:
        return
    user_id = message.from_user.id
    message_text = message.text or ""

    # Показываем индикатор печати
    await message.bot.send_chat_action(
        chat_id=message.chat.id, action=ChatAction.TYPING
    )

    try:
        # Используем user_id как thread_id
        thread_id = str(user_id)

        # Проверяем, есть ли pending media для этого пользователя
        if not bot_instance:
            return
        pending_media = bot_instance.pending_media.get(user_id)

        if pending_media and pending_media["photos"]:
            # Есть изображения - отправляем с изображениями
            logger.info(
                f"Processing message with {len(pending_media['photos'])} images for user {user_id}"
            )

            # Используем текст из сообщения или из подписи к фото
            final_text = message_text or pending_media.get("text", "")

            if not final_text:
                await message.answer(
                    telegramify_markdown.markdownify(
                        "❌ Пожалуйста, отправьте экзаменационный вопрос вместе с фотографиями."
                    ),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

            # Загружаем изображения в API
            image_paths = await bot_instance._upload_images(
                thread_id, pending_media["photos"]
            )

            if not image_paths:
                await message.answer(
                    telegramify_markdown.markdownify(
                        "❌ Ошибка загрузки изображений. Попробуйте еще раз."
                    ),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

            # Отправляем запрос с изображениями через унифицированный метод
            result = await bot_instance._process_message(
                thread_id, final_text, image_paths
            )

            # Очищаем pending media
            del bot_instance.pending_media[user_id]
        else:
            # Нет изображений - обычная обработка
            logger.info(f"Processing text-only message for user {user_id}")
            result = await bot_instance._process_message(thread_id, message_text)

        # Обрабатываем ответ
        await _handle_api_response(message, result)

    except Exception as e:
        logger.error(f"Error processing message from user {user_id}: {e}")
        await message.answer(
            telegramify_markdown.markdownify(
                "❌ Произошла ошибка при обработке. Попробуйте еще раз или используйте /reset."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
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
                chunks = [msg[i : i + 4000] for i in range(0, len(msg), 4000)]
                for chunk in chunks:
                    await message.answer(
                        telegramify_markdown.markdownify(chunk),
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
            else:
                await message.answer(
                    telegramify_markdown.markdownify(msg),
                    parse_mode=ParseMode.MARKDOWN_V2,
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

    # Регистрация роутеров
    dp.include_router(router)
    dp.include_router(hitl_router)
    dp.include_router(prompt_config_router)
    dp.include_router(export_router)

    # Запуск бота
    logger.info("Starting LearnFlow Telegram Bot with image support...")
    await dp.start_polling(bot)


# Методы для работы с API (добавляем в класс LearnFlowBot)


# Методы теперь определены в классе LearnFlowBot


if __name__ == "__main__":
    asyncio.run(main())
