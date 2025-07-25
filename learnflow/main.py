"""
FastAPI сервис для обработки экзаменационных материалов.
REST API эндпойнты для взаимодействия с LangGraph workflow.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from langfuse import Langfuse

from .graph_manager import GraphManager
from .settings import get_settings


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


class ProcessResponse(BaseModel):
    """Модель ответа обработки"""
    thread_id: str = Field(..., description="ID потока")
    result: Any = Field(..., description="Результат обработки")


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


# Создание FastAPI приложения
app = FastAPI(
    title="LearnFlow AI",
    description="Система подготовки экзаменационных материалов на базе LangGraph",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Проверка работы сервиса"""
    return {"message": "LearnFlow AI service is running", "status": "ok"}


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