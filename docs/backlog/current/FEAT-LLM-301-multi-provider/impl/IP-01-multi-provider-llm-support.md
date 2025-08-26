# Implementation Plan: Multi-Provider LLM Support

## Смысл и цель задачи

Реализация поддержки множественных LLM-провайдеров через OpenAI-совместимые API для снижения зависимости от одного вендора и оптимизации стоимости. Решение позволит использовать локальные модели, быстрые облачные сервисы и другие OpenAI-совместимые провайдеры. Основное требование - сохранение работоспособности structured output для узлов, которые его требуют.

## Архитектура решения

**Новые компоненты:**
- `learnflow/config/config_loader.py` - загрузчик YAML с поддержкой Jinja2 шаблонов
- `configs/providers.yaml` - конфигурация всех доступных провайдеров

**Модифицируемые компоненты:**
- `learnflow/config/config_models.py` - добавление ProviderConfig и расширение ModelConfig
- `learnflow/models/model_factory.py` - поддержка base_url и валидация structured output
- `learnflow/config/config_manager.py` - интеграция с загрузчиком Jinja2
- `configs/graph.yaml` - добавление provider и requires_structured_output полей

**Структура файлов:**
```
learnflow/
├── config/
│   ├── config_loader.py      # NEW: Jinja2 loader
│   ├── config_models.py      # MODIFY: Add ProviderConfig
│   └── config_manager.py     # MODIFY: Use Jinja2 loader
├── models/
│   └── model_factory.py      # MODIFY: Add provider support
configs/
├── providers.yaml            # NEW: Providers configuration
└── graph.yaml                # MODIFY: Add provider fields
```

## Полный flow работы функционала

1. **Загрузка конфигурации при старте приложения:**
   - ConfigManager загружает `providers.yaml` через `load_yaml_with_env()`
   - Jinja2 подставляет переменные окружения (API ключи) в конфигурацию
   - Создается словарь ProviderConfig объектов

2. **Инициализация ModelFactory:**
   - ModelFactory получает словарь провайдеров из ConfigManager
   - Сохраняет конфигурации для использования при создании моделей

3. **Создание модели для узла workflow:**
   - Узел запрашивает модель через `create_model_for_node()`
   - ModelFactory получает конфигурацию узла из graph.yaml
   - Проверяет совместимость провайдера с требованиями узла (structured output)
   - Создает ChatOpenAI с соответствующими параметрами (base_url, api_key)

4. **Выполнение запроса к модели:**
   - ChatOpenAI отправляет запрос на указанный base_url или стандартный OpenAI API
   - Для structured output используется метод `with_structured_output()`

## API и интерфейсы

**ProviderConfig:**
- `name` - идентификатор провайдера
- `base_url` - URL для OpenAI-совместимого API (опционально)
- `api_key` - ссылка на переменную окружения через Jinja2
- `supports_structured_output` - поддержка function calling
- `default_model` - модель по умолчанию

**ModelConfig (расширенный):**
- `provider` - имя провайдера из providers.yaml
- `requires_structured_output` - требование structured output для узла
- Остальные поля без изменений

**ModelFactory.create_model():**
- Принимает ModelConfig
- Валидирует совместимость провайдера с требованиями
- Возвращает настроенный ChatOpenAI
- Выбрасывает ValueError при несовместимости

**load_yaml_with_env():**
- Принимает путь к YAML файлу
- Рендерит Jinja2 шаблоны с переменными окружения
- Возвращает словарь с конфигурацией
- Исключение: prompts.yaml загружается без рендеринга

## Взаимодействие компонентов

```
Environment Variables -> Jinja2 Loader -> providers.yaml -> ConfigManager
                                      ↓
                            ProviderConfig Dictionary
                                      ↓
                              ModelFactory
                                      ↓
                            Node requests model
                                      ↓
                     ModelFactory validates requirements
                                      ↓
                     Creates ChatOpenAI with base_url
                                      ↓
                         API call to provider
```

## Порядок реализации

### Шаг 1: Создание загрузчика конфигурации с Jinja2

Создать файл `learnflow/config/config_loader.py`:

```python
import os
import yaml
from jinja2 import Template
from typing import Dict, Any

def load_yaml_with_env(path: str) -> Dict[str, Any]:
    """
    Загружает YAML-файл с подстановкой переменных окружения через Jinja2.
    
    Args:
        path: Путь к YAML-файлу
        
    Returns:
        dict: Загруженная конфигурация с подставленными переменными
    """
    # Проверяем, является ли файл prompts.yaml
    if path.endswith("prompts.yaml"):
        # Для файла prompts.yaml не рендерим шаблоны Jinja2
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f.read())
    else:
        # Для остальных файлов применяем подстановку переменных окружения
        with open(path, "r", encoding="utf-8") as f:
            template = Template(f.read())
            rendered = template.render(env=os.environ)
            return yaml.safe_load(rendered)
```

### Шаг 2: Добавление моделей конфигурации

Обновить `learnflow/config/config_models.py`, добавив в начало файла:

```python
class ProviderConfig(BaseModel):
    """Configuration for OpenAI-compatible providers"""
    name: str = Field(description="Provider name (e.g., 'openai', 'openrouter')")
    base_url: Optional[str] = Field(default=None, description="Base URL for OpenAI-compatible API")
    api_key: Optional[str] = Field(default=None, description="API key reference (uses Jinja2 template)") 
    supports_structured_output: bool = Field(
        default=False, 
        description="Whether this provider supports structured output (function calling)"
    )
    default_model: Optional[str] = Field(default=None, description="Default model for this provider")
```

И расширить существующий ModelConfig:

```python
class ModelConfig(BaseModel):
    """Enhanced model configuration with provider support"""
    provider: str = Field(default="openai", description="Provider name from providers config")
    model_name: str = Field(description="Model name")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, gt=0)
    
    # Optional parameters (already supported)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    
    # Node requirements
    requires_structured_output: bool = Field(default=False, description="Node requires structured output support")
```

### Шаг 3: Обновление ModelFactory

Полностью заменить содержимое `learnflow/models/model_factory.py`:

```python
import logging
from typing import Optional, Dict
from langchain_openai import ChatOpenAI
from ..config.config_manager import get_config_manager
from ..config.config_models import ModelConfig, ProviderConfig

logger = logging.getLogger(__name__)

class ModelFactory:
    """Factory for creating LLM models with OpenAI-compatible provider support"""
    
    def __init__(self, providers_config: Dict[str, ProviderConfig]):
        """
        Initialize the model factory.
        
        Args:
            providers_config: Dictionary of provider configurations
        """
        self.providers_config = providers_config
    
    def create_model(self, config: ModelConfig) -> ChatOpenAI:
        """
        Create a ChatOpenAI model with provider-specific configuration.
        
        Args:
            config: Model configuration
            
        Returns:
            Configured ChatOpenAI instance
        """
        # Получаем конфигурацию провайдера
        provider_config = self.providers_config.get(config.provider, ProviderConfig(name="openai"))
        
        # Проверяем поддержку structured output
        if config.requires_structured_output and not provider_config.supports_structured_output:
            raise ValueError(
                f"Provider '{config.provider}' does not support structured output required by this node. "
                f"Please use a provider with structured output support (e.g., 'openai', 'fireworks')"
            )
        
        # Собираем параметры для ChatOpenAI
        model_params = {
            "model": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        
        # Добавляем API key (приоритет: provider config -> default)
        api_key = provider_config.api_key
        if api_key:
            model_params["openai_api_key"] = api_key
        
        # Добавляем base_url если указан
        if provider_config.base_url:
            model_params["openai_api_base"] = provider_config.base_url
        
        # Добавляем опциональные параметры генерации
        if config.top_p is not None:
            model_params["top_p"] = config.top_p
        if config.frequency_penalty is not None:
            model_params["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty is not None:
            model_params["presence_penalty"] = config.presence_penalty
        
        logger.debug(
            f"Creating model for provider '{config.provider}' with model '{config.model_name}', "
            f"base_url='{provider_config.base_url}'"
        )
        
        return ChatOpenAI(**model_params)
    
    def create_model_for_node(self, node_name: str) -> ChatOpenAI:
        """
        Create a model for a specific workflow node.
        
        Args:
            node_name: Name of the workflow node
            
        Returns:
            Configured ChatOpenAI instance for the node
        """
        config_manager = get_config_manager()
        config = config_manager.get_model_config(node_name)
        
        if not config_manager.has_node_config(node_name):
            logger.warning(
                f"No specific configuration found for node '{node_name}', using default configuration"
            )
        
        return self.create_model(config)

# Global factory instance
_model_factory: Optional[ModelFactory] = None

def initialize_model_factory(api_key: str = None, config_manager=None) -> ModelFactory:
    """
    Initialize the global model factory with provider support.
    API keys берутся из конфигурации провайдеров (уже с подставленными env переменными).
    
    Args:
        api_key: Fallback OpenAI API key (для обратной совместимости)
        config_manager: Optional config manager
        
    Returns:
        ModelFactory instance
    """
    global _model_factory
    
    # Загружаем конфигурацию провайдеров (уже с подставленными API ключами)
    config_manager = config_manager or get_config_manager()
    providers_config = config_manager.get_providers_config()
    
    _model_factory = ModelFactory(providers_config)
    return _model_factory

def get_model_factory() -> ModelFactory:
    """Get the global model factory instance."""
    if _model_factory is None:
        raise RuntimeError("Model factory not initialized. Call initialize_model_factory() first.")
    return _model_factory
```

### Шаг 4: Обновление ConfigManager

Добавить в начало `learnflow/config/config_manager.py`:

```python
from .config_loader import load_yaml_with_env
from .config_models import ProviderConfig
```

И добавить методы в класс ConfigManager:

```python
def __init__(self, graph_path: str = None, prompts_path: str = None, providers_path: str = None):
    """Initialize configuration manager with optional config paths."""
    self.graph_config = {}
    self.prompts_config = {}
    self.providers_config = {}
    
    if graph_path:
        self.graph_config = load_yaml_with_env(graph_path)
    if prompts_path:
        self.prompts_config = load_yaml_with_env(prompts_path)
    if providers_path:
        self.providers_config = load_yaml_with_env(providers_path)

def get_providers_config(self) -> Dict[str, ProviderConfig]:
    """Возвращает конфигурацию провайдеров с уже подставленными API ключами"""
    providers = {}
    for name, config in self.providers_config.get("providers", {}).items():
        providers[name] = ProviderConfig(**config)
    return providers
```

### Шаг 5: Создание файла конфигурации провайдеров

Создать файл `configs/providers.yaml`:

```yaml
providers:
  # OpenAI - официальный API
  openai:
    name: openai
    api_key: "{{ env.OPENAI_API_KEY }}"
    # base_url не указан - используется стандартный OpenAI API
    supports_structured_output: true
    default_model: gpt-4.1-mini

  fireworks:
    name: fireworks
    api_key: "{{ env.FIREWORKS_API_KEY }}"
    base_url: https://api.fireworks.ai/inference/v1
    supports_structured_output: true
    default_model: accounts/fireworks/models/qwen3-235b-a22b-instruct-2507
  
  # OpenRouter - агрегатор различных моделей
  openrouter:
    name: openrouter
    api_key: "{{ env.OPENROUTER_API_KEY }}"
    base_url: https://openrouter.ai/api/v1
    supports_structured_output: false  # Зависит от модели
    default_model: openai/gpt-4.1-mini
```

### Шаг 6: Обновление graph.yaml

Обновить `configs/graph.yaml`, добавив поля provider и requires_structured_output:

```yaml
models:
  default:
    provider: openai  # По умолчанию используем OpenAI
    model_name: gpt-4.1-mini
    temperature: 0.1
    max_tokens: 4000
  
  nodes:
    # Узлы без structured output - можно использовать любого OpenAI-совместимого провайдера
    generating_content:
      provider: openrouter
      model_name: openai/gpt-4.1-mini
      temperature: 0.2
      max_tokens: 8000
    
    synthesis_material:
      provider: openrouter
      model_name: openai/gpt-4.1-mini
      temperature: 0.1
      max_tokens: 8000
    
    # Узлы со structured output - только провайдеры с поддержкой
    generating_questions:
      provider: openai  # Требует structured output
      model_name: gpt-4.1-mini
      temperature: 0.3
      max_tokens: 3000
      requires_structured_output: true
    
    edit_material:
      provider: fireworks
      model_name: accounts/fireworks/models/qwen3-235b-a22b-instruct-2507
      temperature: 0.2
      max_tokens: 6000
      requires_structured_output: true
    
    security_guard:
      provider: openai
      model_name: gpt-4.1-mini
      temperature: 0.0
      max_tokens: 1000
      requires_structured_output: true
```

### Шаг 7: Обновление инициализации в main.py

Найти инициализацию ConfigManager и ModelFactory в `learnflow/main.py` и обновить:

```python
# Добавить путь к providers.yaml при инициализации ConfigManager
config_manager = ConfigManager(
    graph_path="configs/graph.yaml",
    prompts_path="configs/prompts.yaml",
    providers_path="configs/providers.yaml"  # NEW
)

# ModelFactory теперь инициализируется с провайдерами
model_factory = initialize_model_factory(
    api_key=settings.OPENAI_API_KEY,  # Fallback для обратной совместимости
    config_manager=config_manager
)
```

### Шаг 8: Обновление переменных окружения

Добавить в `.env` новые переменные для провайдеров:

```bash
# API Keys для различных провайдеров
OPENROUTER_API_KEY=your_openrouter_api_key

# Кастомный провайдер (опционально)
CUSTOM_API_KEY=your_custom_api_key
CUSTOM_LLM_BASE_URL=https://your-custom-api.com/v1
```

### Шаг 9: Установка Jinja2

Добавить зависимость в `pyproject.toml` если её еще нет:

```toml
[tool.uv.sources.learnflow]
dependencies = [
    # ... existing dependencies
    "jinja2>=3.1.0",
]
```

И выполнить:
```bash
uv sync --package learnflow
```

## Критичные граничные случаи

**Провайдер не поддерживает structured output:**
- ModelFactory выбросит ValueError при попытке создать модель
- Решение: использовать провайдер с поддержкой или изменить конфигурацию узла

**Отсутствует API ключ для провайдера:**
- ChatOpenAI попытается использовать переменную окружения OPENAI_API_KEY
- Если и она отсутствует, будет ошибка при первом вызове API

**Недоступен base_url провайдера:**
- Ошибка соединения при вызове API
- Нет автоматического fallback на другой провайдер (MVP не требует)

**Несовместимость модели с провайдером:**
- Ошибка от API провайдера о неизвестной модели
- Решение: проверить корректность имени модели для данного провайдера