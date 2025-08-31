"""
FastAPI сервис для обработки учебных материалов.
REST API эндпойнты для взаимодействия с LangGraph workflow.
"""

import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from langfuse import Langfuse

from ..core.graph_manager import GraphManager
from ..config.settings import get_settings
from ..services.file_utils import ImageFileManager, ensure_temp_storage
from ..config.config_manager import initialize_config_manager
from ..models.model_factory import initialize_model_factory
from ..services.hitl_manager import get_hitl_manager
from ..models.hitl_config import HITLConfig


# Создаем директорию для логов если её нет
Path("logs").mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Консоль
        logging.FileHandler("logs/learnflow.log", encoding="utf-8"),  # Файл
    ],
)
logger = logging.getLogger(__name__)

# Глобальный экземпляр менеджера
graph_manager: Optional[GraphManager] = None


class ProcessRequest(BaseModel):
    """Модель запроса для обработки"""

    thread_id: Optional[str] = Field(
        default=None, description="ID потока (опционально)"
    )
    message: str = Field(..., description="Сообщение для обработки")
    image_paths: Optional[List[str]] = Field(
        default=None, description="Пути к загруженным изображениям (опционально)"
    )


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
    state: Optional[Dict[str, Any]] = Field(
        default=None, description="Текущее состояние"
    )
    current_step: Dict[str, Any] = Field(..., description="Текущий шаг")


class NodeSettingRequest(BaseModel):
    """Модель запроса для обновления настройки узла"""

    enabled: bool = Field(..., description="Включить/выключить HITL для узла")


class BulkUpdateRequest(BaseModel):
    """Модель запроса для массового обновления HITL"""

    enable_all: bool = Field(..., description="Включить/выключить HITL для всех узлов")


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
        initialize_model_factory(settings.openai_api_key, config_manager)
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
    description="Система подготовки учебных материалов на базе LangGraph с поддержкой изображений",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Проверка работы сервиса"""
    return {
        "message": "LearnFlow AI service is running",
        "status": "ok",
        "features": ["text_processing", "image_recognition"],
    }


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
async def upload_images(thread_id: str, files: List[UploadFile] = File(...)):
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
                detail=f"Too many files: {len(files)} > {settings.max_images_per_request}",
            )

        # Проверяем каждый файл
        image_data_list = []
        for file in files:
            # Проверяем тип файла
            if not file.content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type: {file.content_type}. Only images are allowed.",
                )

            # Читаем содержимое файла
            content = await file.read()

            # Проверяем размер
            if len(content) > settings.max_image_size:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} too large: {len(content)} > {settings.max_image_size}",
                )

            image_data_list.append(content)

        # Сохраняем изображения
        file_manager = ImageFileManager()
        saved_paths = file_manager.save_uploaded_images(thread_id, image_data_list)

        logger.info(
            f"Successfully uploaded {len(saved_paths)} images for thread {thread_id}"
        )

        return UploadResponse(
            thread_id=thread_id,
            uploaded_files=saved_paths,
            message=f"Successfully uploaded {len(saved_paths)} images",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading images for thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")

@app.post("/process", response_model=ProcessResponse)
async def process_request(request: ProcessRequest):
    """
    Универсальный эндпойнт для обработки учебного материала.
    Поддерживает все сценарии: с изображениями, текстовыми конспектами и без них.

    Args:
        request: Запрос с thread_id (опционально), сообщением и изображениями (опционально)

    Returns:
        ProcessResponse: Результат обработки с thread_id

    Raises:
        HTTPException: При ошибках обработки
    """
    if graph_manager is None:
        raise HTTPException(status_code=503, detail="GraphManager not available")

    try:
        logger.info(f"Processing request for thread: {request.thread_id}")
        
        # Валидируем изображения если они есть
        valid_paths = None
        if request.image_paths:
            logger.debug(f"Processing with {len(request.image_paths)} image paths")
            file_manager = ImageFileManager()
            from pathlib import Path
            
            valid_paths = []
            for path in request.image_paths:
                path_obj = Path(path)
                if path_obj.exists() and file_manager.validate_image_file(path_obj):
                    valid_paths.append(path)
                else:
                    logger.warning(f"Invalid image path: {path}")
            
            if valid_paths:
                logger.info(f"Validated {len(valid_paths)} images for processing")

        result = await graph_manager.process_step(
            thread_id=request.thread_id or "", 
            query=request.message,
            image_paths=valid_paths  # Передаем изображения в унифицированный метод
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
            thread_id=thread_id, state=state, current_step=current_step
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
            logger.warning(
                f"Failed to cleanup temp files for thread {thread_id}: {cleanup_error}"
            )

        logger.info(f"Thread {thread_id} deleted successfully")

        return {"message": f"Thread {thread_id} deleted successfully"}

    except Exception as e:
        logger.error(f"Error deleting thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion error: {str(e)}")


# HITL Configuration API Endpoints


@app.get("/api/hitl/{thread_id}", response_model=HITLConfig)
async def get_hitl_config(thread_id: str):
    """
    Получить текущую конфигурацию HITL для потока

    Args:
        thread_id: ID потока пользователя

    Returns:
        HITLConfig: Текущая конфигурация HITL
    """
    try:
        hitl_manager = get_hitl_manager()
        config = hitl_manager.get_config(thread_id)
        logger.info(f"Retrieved HITL config for thread {thread_id}: {config.to_dict()}")
        return config

    except Exception as e:
        logger.error(f"Error getting HITL config for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get HITL config: {str(e)}"
        )


@app.put("/api/hitl/{thread_id}", response_model=HITLConfig)
async def set_hitl_config(thread_id: str, config: HITLConfig):
    """
    Установить полную конфигурацию HITL для потока

    Args:
        thread_id: ID потока пользователя
        config: Новая конфигурация HITL

    Returns:
        HITLConfig: Установленная конфигурация HITL
    """
    try:
        hitl_manager = get_hitl_manager()
        hitl_manager.set_config(thread_id, config)
        logger.info(f"Set HITL config for thread {thread_id}: {config.to_dict()}")
        return config

    except Exception as e:
        logger.error(f"Error setting HITL config for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to set HITL config: {str(e)}"
        )


@app.patch("/api/hitl/{thread_id}/node/{node_name}", response_model=HITLConfig)
async def update_node_hitl(thread_id: str, node_name: str, request: NodeSettingRequest):
    """
    Обновить настройку HITL для конкретного узла

    Args:
        thread_id: ID потока пользователя
        node_name: Имя узла
        request: Запрос с новой настройкой

    Returns:
        HITLConfig: Обновленная конфигурация HITL
    """
    try:
        hitl_manager = get_hitl_manager()
        updated_config = hitl_manager.update_node_setting(
            thread_id, node_name, request.enabled
        )
        logger.info(
            f"Updated node {node_name} to {request.enabled} for thread {thread_id}"
        )
        return updated_config

    except Exception as e:
        logger.error(f"Error updating node {node_name} for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to update node setting: {str(e)}"
        )


@app.post("/api/hitl/{thread_id}/reset", response_model=HITLConfig)
async def reset_hitl_config(thread_id: str):
    """
    Сбросить конфигурацию к значениям по умолчанию

    Args:
        thread_id: ID потока пользователя

    Returns:
        HITLConfig: Сброшенная конфигурация HITL
    """
    try:
        hitl_manager = get_hitl_manager()
        hitl_manager.reset_config(thread_id)
        config = hitl_manager.get_config(thread_id)
        logger.info(f"Reset HITL config for thread {thread_id}")
        return config

    except Exception as e:
        logger.error(f"Error resetting HITL config for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reset HITL config: {str(e)}"
        )


@app.post("/api/hitl/{thread_id}/bulk", response_model=HITLConfig)
async def bulk_update_hitl(thread_id: str, request: BulkUpdateRequest):
    """
    Включить или выключить HITL для всех узлов

    Args:
        thread_id: ID потока пользователя
        request: Запрос с флагом для всех узлов

    Returns:
        HITLConfig: Обновленная конфигурация HITL
    """
    try:
        hitl_manager = get_hitl_manager()
        updated_config = hitl_manager.bulk_update(thread_id, request.enable_all)
        logger.info(f"Bulk updated HITL to {request.enable_all} for thread {thread_id}")
        return updated_config

    except Exception as e:
        logger.error(f"Error bulk updating HITL for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to bulk update HITL: {str(e)}"
        )


@app.get("/api/hitl/debug/all-configs")
async def get_all_hitl_configs():
    """
    Получить все конфигурации HITL (для отладки)

    Returns:
        Dict: Все конфигурации HITL по thread_id
    """
    try:
        hitl_manager = get_hitl_manager()
        all_configs = hitl_manager.get_all_configs()
        # Convert HITLConfig objects to dict for JSON serialization
        serialized_configs = {
            thread_id: config.to_dict() for thread_id, config in all_configs.items()
        }
        logger.info(f"Retrieved all HITL configs: {len(serialized_configs)} threads")
        return {"configs": serialized_configs}

    except Exception as e:
        logger.error(f"Error getting all HITL configs: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get all configs: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик исключений"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "learnflow.api.main:app", 
        host=settings.host, 
        port=settings.port
    )
