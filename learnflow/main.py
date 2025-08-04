"""
FastAPI сервис для обработки экзаменационных материалов.
REST API эндпойнты для взаимодействия с LangGraph workflow.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from langfuse import Langfuse

from .graph_manager import GraphManager
from .settings import get_settings
from .file_utils import ImageFileManager, ensure_temp_storage
from .config_manager import initialize_config_manager
from .model_factory import initialize_model_factory


# Настройка логирования
logging.basicConfig(
    level=get_settings().log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Консоль
        logging.FileHandler('learnflow.log', encoding='utf-8')  # Файл
    ]
)
logger = logging.getLogger(__name__)

# Глобальный экземпляр менеджера
graph_manager: Optional[GraphManager] = None


class ProcessRequest(BaseModel):
    """Модель запроса для обработки"""
    thread_id: Optional[str] = Field(default=None, description="ID потока (опционально)")
    message: str = Field(..., description="Сообщение для обработки")


class ProcessWithImagesRequest(BaseModel):
    """Модель запроса для обработки с изображениями"""
    thread_id: str = Field(..., description="ID потока")
    message: str = Field(..., description="Экзаменационный вопрос")
    image_paths: List[str] = Field(default_factory=list, description="Пути к загруженным изображениям")


class ProcessResponse(BaseModel):
    """Модель ответа обработки"""
    thread_id: str = Field(..., description="ID потока")
    result: Any = Field(..., description="Результат обработки")


class UploadResponse(BaseModel):
    """Модель ответа загрузки изображений"""
    thread_id: str = Field(..., description="ID потока")
    uploaded_files: List[str] = Field(..., description="Пути к загруженным файлам")
    message: str = Field(..., description="Сообщение о результате")


class StateResponse(BaseModel):
    """Модель ответа состояния"""
    thread_id: str = Field(..., description="ID потока")
    state: Optional[Dict[str, Any]] = Field(default=None, description="Текущее состояние")
    current_step: Dict[str, Any] = Field(..., description="Текущий шаг")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global graph_manager
    
    logger.info("Starting LearnFlow AI service...")
    
    # Инициализация настроек
    settings = get_settings()
    
    # Инициализация конфигурационного менеджера
    try:
        config_manager = initialize_config_manager(settings.graph_config_path)
        logger.info(f"Graph configuration loaded from {settings.graph_config_path}")
    except Exception as e:
        logger.error(f"Failed to load graph configuration: {e}")
        raise
    
    # Инициализация фабрики моделей
    try:
        model_factory = initialize_model_factory(settings.openai_api_key, config_manager)
        logger.info("Model factory initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize model factory: {e}")
        raise
    
    # Создание временных директорий
    ensure_temp_storage()
    logger.info("Temporary storage initialized")
    
    # Проверка LangFuse подключения
    try:
        langfuse = Langfuse()
        if langfuse.auth_check():
            logger.info("LangFuse client authenticated successfully")
        else:
            logger.warning("LangFuse authentication failed")
    except Exception as e:
        logger.warning(f"LangFuse initialization error: {e}")
    
    # Инициализация GraphManager
    graph_manager = GraphManager()
    logger.info("GraphManager initialized successfully")
    
    yield
    
    logger.info("Shutting down LearnFlow AI service...")
    
    # Очистка временных файлов при выключении
    # Можно добавить логику очистки здесь если нужно


# Создание FastAPI приложения
app = FastAPI(
    title="LearnFlow AI",
    description="Система подготовки экзаменационных материалов на базе LangGraph с поддержкой изображений",
    version="1.1.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Проверка работы сервиса"""
    return {"message": "LearnFlow AI service is running", "status": "ok", "features": ["text_processing", "image_recognition"]}


@app.get("/health")
async def health_check():
    """Health probe для мониторинга"""
    try:
        # Проверяем доступность GraphManager
        if graph_manager is None:
            raise HTTPException(status_code=503, detail="GraphManager not initialized")
        
        return {"status": "healthy", "service": "learnflow-ai"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@app.post("/upload-images/{thread_id}", response_model=UploadResponse)
async def upload_images(
    thread_id: str,
    files: List[UploadFile] = File(...)
):
    """
    Загрузка изображений конспектов для thread_id.
    
    Args:
        thread_id: ID потока
        files: Список загружаемых файлов изображений
        
    Returns:
        UploadResponse: Информация о загруженных файлах
        
    Raises:
        HTTPException: При ошибках загрузки или валидации
    """
    try:
        logger.info(f"Uploading {len(files)} images for thread {thread_id}")
        
        # Проверяем количество файлов
        settings = get_settings()
        if len(files) > settings.max_images_per_request:
            raise HTTPException(
                status_code=400, 
                detail=f"Too many files: {len(files)} > {settings.max_images_per_request}"
            )
        
        # Проверяем каждый файл
        image_data_list = []
        for file in files:
            # Проверяем тип файла
            if not file.content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type: {file.content_type}. Only images are allowed."
                )
            
            # Читаем содержимое файла
            content = await file.read()
            
            # Проверяем размер
            if len(content) > settings.max_image_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} too large: {len(content)} > {settings.max_image_size}"
                )
            
            image_data_list.append(content)
        
        # Сохраняем изображения
        file_manager = ImageFileManager()
        saved_paths = file_manager.save_uploaded_images(thread_id, image_data_list)
        
        logger.info(f"Successfully uploaded {len(saved_paths)} images for thread {thread_id}")
        
        return UploadResponse(
            thread_id=thread_id,
            uploaded_files=saved_paths,
            message=f"Successfully uploaded {len(saved_paths)} images"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading images for thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@app.post("/process-with-images", response_model=ProcessResponse)
async def process_with_images(request: ProcessWithImagesRequest):
    """
    Запуск обработки экзаменационного материала с изображениями.
    
    Args:
        request: Запрос с thread_id, сообщением и путями к изображениям
        
    Returns:
        ProcessResponse: Результат обработки
        
    Raises:
        HTTPException: При ошибках обработки
    """
    if graph_manager is None:
        raise HTTPException(status_code=503, detail="GraphManager not available")
    
    try:
        logger.info(f"Processing request with images for thread: {request.thread_id}")
        logger.debug(f"Image paths: {request.image_paths}")
        
        # Валидируем изображения
        if request.image_paths:
            file_manager = ImageFileManager()
            from pathlib import Path
            valid_paths = []
            for path in request.image_paths:
                path_obj = Path(path)
                if path_obj.exists() and file_manager.validate_image_file(path_obj):
                    valid_paths.append(path)
                else:
                    logger.warning(f"Invalid image path: {path}")
            request.image_paths = valid_paths
        
        result = await graph_manager.process_step_with_images(
            thread_id=request.thread_id,
            query=request.message,
            image_paths=request.image_paths
        )
        
        return ProcessResponse(**result)
        
    except Exception as e:
        logger.error(f"Error processing request with images: {e}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@app.post("/process", response_model=ProcessResponse)
async def process_request(request: ProcessRequest):
    """
    Запуск/продолжение обработки экзаменационного материала.
    
    Args:
        request: Запрос с thread_id (опционально) и сообщением
        
    Returns:
        ProcessResponse: Результат обработки с thread_id
        
    Raises:
        HTTPException: При ошибках обработки
    """
    if graph_manager is None:
        raise HTTPException(status_code=503, detail="GraphManager not available")
    
    try:
        logger.info(f"Processing request for thread: {request.thread_id}")
        
        result = await graph_manager.process_step(
            thread_id=request.thread_id or "",
            query=request.message
        )
        
        return ProcessResponse(**result)
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@app.get("/state/{thread_id}", response_model=StateResponse)
async def get_state(thread_id: str):
    """
    Получение текущего состояния потока.
    
    Args:
        thread_id: ID потока
        
    Returns:
        StateResponse: Текущее состояние и шаг
        
    Raises:
        HTTPException: При ошибках получения состояния
    """
    if graph_manager is None:
        raise HTTPException(status_code=503, detail="GraphManager not available")
    
    try:
        # Получаем состояние и текущий шаг
        state = await graph_manager.get_thread_state(thread_id)
        current_step = await graph_manager.get_current_step(thread_id)
        
        return StateResponse(
            thread_id=thread_id,
            state=state,
            current_step=current_step
        )
        
    except Exception as e:
        logger.error(f"Error getting state for thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"State retrieval error: {str(e)}")


@app.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str):
    """
    Удаление потока и всех связанных данных.
    
    Args:
        thread_id: ID потока для удаления
        
    Returns:
        Dict: Результат удаления
        
    Raises:
        HTTPException: При ошибках удаления
    """
    if graph_manager is None:
        raise HTTPException(status_code=503, detail="GraphManager not available")
    
    try:
        await graph_manager.delete_thread(thread_id)
        
        # Очищаем временные файлы для этого потока
        try:
            file_manager = ImageFileManager()
            file_manager.cleanup_temp_directory(thread_id)
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup temp files for thread {thread_id}: {cleanup_error}")
        
        logger.info(f"Thread {thread_id} deleted successfully")
        
        return {"message": f"Thread {thread_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion error: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик исключений"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "learnflow.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    ) 