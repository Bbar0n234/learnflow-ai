# FEAT-LLM-301: Поддержка локальных LLM

## Статус
Active

## Milestone
Pre-OSS Release

## Цель
Обеспечить работу LearnFlow AI с любыми OpenAI-совместимыми API, включая локальные модели (Ollama, LM Studio, vLLM).

## Обоснование
- Снижение зависимости от облачных провайдеров
- Экономия на API costs для разработчиков
- Возможность работы в offline/restricted environments
- Привлечение privacy-conscious пользователей
- Демонстрация гибкости архитектуры

## План реализации

### Этап 1: Абстракция провайдеров (2 дня)
- [ ] Создать интерфейс `LLMProvider` protocol
- [ ] Реализовать `OpenAIProvider` (существующий)
- [ ] Добавить `BaseProvider` с общей логикой
- [ ] Рефакторинг существующего кода под новую абстракцию

### Этап 2: Ollama интеграция (2 дня)
- [ ] Создать `OllamaProvider` класс
- [ ] Реализовать автоопределение доступных моделей
- [ ] Добавить поддержку streaming
- [ ] Написать интеграционные тесты

### Этап 3: LM Studio поддержка (1 день)
- [ ] Создать `LMStudioProvider` класс
- [ ] Добавить конфигурацию через ENV
- [ ] Тестирование с популярными моделями

### Этап 4: Docker-образы с моделями (3 дня)
- [ ] Создать Dockerfile с llama.cpp
- [ ] Добавить docker-compose профиль для локальных LLM
- [ ] Скрипт для автоматической загрузки моделей
- [ ] Документация по настройке

### Этап 5: Fallback и routing (2 дня)
- [ ] Реализовать fallback механизм между провайдерами
- [ ] Добавить health checks для провайдеров
- [ ] Интеллектуальный routing based on model capabilities
- [ ] Метрики использования провайдеров

## Технические требования

### Архитектура
```python
learnflow/llm/
├── __init__.py
├── base.py           # Protocol и базовые классы
├── providers/
│   ├── openai.py    # OpenAI/Azure
│   ├── ollama.py    # Ollama
│   ├── lmstudio.py  # LM Studio
│   ├── vllm.py      # vLLM
│   └── custom.py    # Custom endpoints
├── router.py         # Routing и fallback
└── utils.py         # Helpers
```

### Конфигурация
```bash
# .env examples

# Ollama (local)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:latest

# LM Studio
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=local-model

# Multiple providers with fallback
LLM_PROVIDERS=openai,ollama
LLM_FALLBACK_ENABLED=true
```

### Docker Compose профиль
```yaml
# docker-compose.yml
services:
  ollama:
    profiles: [local-llm]
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### Provider Interface
```python
from typing import Protocol, AsyncIterator

class LLMProvider(Protocol):
    """Unified interface for all LLM providers"""
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """Generate text completion"""
        ...
    
    async def stream(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream text completion"""
        ...
    
    async def health_check(self) -> bool:
        """Check if provider is available"""
        ...
    
    def get_capabilities(self) -> dict:
        """Return provider capabilities"""
        ...
```

## Definition of Done

- [ ] Минимум 3 локальных провайдера поддерживаются
- [ ] Автоматическое определение доступных провайдеров
- [ ] Fallback работает без потери данных
- [ ] Docker Compose с предустановленной локальной моделью
- [ ] Документация по настройке каждого провайдера
- [ ] Интеграционные тесты для всех провайдеров
- [ ] Пример конфигурации в env.example

## Риски
- Разные провайдеры могут иметь несовместимые особенности
- Локальные модели требуют значительных ресурсов
- Качество ответов может варьироваться между моделями

## Зависимости
- httpx для async HTTP запросов
- Docker для контейнеризации моделей
- CUDA/Metal для GPU ускорения (опционально)

## Метрики успеха
- Количество поддерживаемых провайдеров
- Время переключения при fallback
- Успешность health checks
- Латентность разных провайдеров

## Примеры использования

```python
# Автоматический выбор провайдера
from learnflow.llm import get_provider

provider = get_provider()  # Выберет на основе ENV
response = await provider.generate("Explain cryptography")

# Явный выбор провайдера
from learnflow.llm.providers import OllamaProvider

ollama = OllamaProvider(base_url="http://localhost:11434")
response = await ollama.generate(
    "Explain RSA encryption",
    model="llama3:latest"
)

# С fallback
from learnflow.llm import RouterProvider

router = RouterProvider(
    primary="openai",
    fallback=["ollama", "lmstudio"]
)
response = await router.generate("Complex query")
```

## Ссылки
- [Ollama Documentation](https://ollama.ai/)
- [LM Studio](https://lmstudio.ai/)
- [vLLM](https://github.com/vllm-project/vllm)
- [OpenAI API Spec](https://platform.openai.com/docs/api-reference)