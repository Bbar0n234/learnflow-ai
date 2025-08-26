# Multi-Provider LLM Support Architecture (OpenAI-Compatible)

## Анализ текущей ситуации

### Использование моделей в приложении

После анализа кодовой базы выявлено два основных паттерна использования LLM:

1. **Обычные вызовы моделей** (regular model calls):
   - Используются в большинстве узлов workflow
   - Работают через `ChatOpenAI` без специфичных параметров
   - Примеры: `generating_content`, `synthesis_material`, `answer_question`

2. **Структурированный вывод** (structured output):
   - Метод `with_structured_output()` из LangChain
   - Использует OpenAI Function Calling под капотом
   - Требует поддержки `response_format` или `tools/functions` параметров
   - Примеры использования:
     - `learnflow/nodes/questions.py:80` - `GapQuestions` и `GapQuestionsHITL`
     - `learnflow/nodes/edit_material.py:251` - `ActionDecision`, `EditDetails`, `EditMessageDetails`
     - `learnflow/security/guard.py:35` - `InjectionResult`

### Текущая архитектура

```
learnflow/
├── models/
│   └── model_factory.py       # Фабрика для создания моделей (только OpenAI)
├── config/
│   ├── config_models.py       # Pydantic модели конфигурации
│   └── config_manager.py      # Менеджер конфигурации
└── nodes/
    ├── base.py                # Базовый класс с create_model()
    └── [различные узлы]       # Используют self.create_model()
```

Конфигурация в `configs/graph.yaml`:
- Только `model_name` и параметры генерации
- Нет поддержки различных провайдеров через base_url
- Все узлы используют OpenAI API напрямую

## Предлагаемое решение

### 1. Расширенная модель конфигурации

```python
# learnflow/config/config_models.py

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class ProviderConfig(BaseModel):
    """Configuration for OpenAI-compatible providers"""
    name: str = Field(description="Provider name (e.g., 'openai', 'ollama', 'groq')")
    base_url: Optional[str] = Field(default=None, description="Base URL for OpenAI-compatible API")
    api_key: Optional[str] = Field(default=None, description="API key reference (uses Jinja2 template)") 
    supports_structured_output: bool = Field(
        default=False, 
        description="Whether this provider supports structured output (function calling)"
    )
    default_model: Optional[str] = Field(default=None, description="Default model for this provider")

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

### 2. Упрощенная фабрика моделей с поддержкой base_url

```python
# learnflow/models/model_factory.py (обновленная версия существующего файла)

import logging
from typing import Optional, Dict
from langchain_openai import ChatOpenAI
from ..config.config_manager import get_config_manager
from ..config.config_models import ModelConfig, ProviderConfig

logger = logging.getLogger(__name__)

class ModelFactory:
    """Factory for creating LLM models with OpenAI-compatible provider support"""
    
    def __init__(self, providers_config: Dict[str, ProviderConfig], default_api_key: str = None):
        """
        Initialize the model factory.
        
        Args:
            providers_config: Dictionary of provider configurations
            default_api_key: Default OpenAI API key (for backward compatibility)
        """
        self.providers_config = providers_config
        self.default_api_key = default_api_key
    
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
                f"Please use a provider with structured output support (e.g., 'openai', 'groq-tools')"
            )
        
        # Собираем параметры для ChatOpenAI
        model_params = {
            "model": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        
        # Добавляем API key (приоритет: provider config -> default)
        api_key = provider_config.api_key or self.default_api_key
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
```

### 3. Обновленная конфигурация с поддержкой Jinja2 шаблонов

```yaml
# configs/providers.yaml
providers:
  # OpenAI - официальный API
  openai:
    name: openai
    api_key: "{{ env.OPENAI_API_KEY }}"
    # base_url не указан - используется стандартный OpenAI API
    supports_structured_output: true
    default_model: gpt-4o-mini
  
  # Ollama - локальные модели (без API ключа)
  ollama:
    name: ollama
    base_url: http://localhost:11434/v1
    supports_structured_output: false  # Большинство локальных моделей не поддерживают
    default_model: llama3.2
  
  # Groq - быстрый инференс
  groq:
    name: groq
    api_key: "{{ env.GROQ_API_KEY }}"
    base_url: https://api.groq.com/openai/v1
    supports_structured_output: false  # Базовые модели не поддерживают
    default_model: llama-3.1-70b-versatile
  
  # Groq с поддержкой tools (для structured output)
  groq-tools:
    name: groq-tools
    api_key: "{{ env.GROQ_API_KEY }}"  # Используем тот же ключ
    base_url: https://api.groq.com/openai/v1
    supports_structured_output: true  # Специальные модели с поддержкой tools
    default_model: llama3-groq-70b-8192-tool-use-preview
  
  # Together AI
  together:
    name: together
    api_key: "{{ env.TOGETHER_API_KEY }}"
    base_url: https://api.together.xyz/v1
    supports_structured_output: false
    default_model: meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
  
  # OpenRouter - агрегатор различных моделей
  openrouter:
    name: openrouter
    api_key: "{{ env.OPENROUTER_API_KEY }}"
    base_url: https://openrouter.ai/api/v1
    supports_structured_output: true  # Зависит от модели
    default_model: openai/gpt-4o-mini
  
  # Кастомный OpenAI-совместимый сервер
  custom:
    name: custom
    api_key: "{{ env.CUSTOM_API_KEY }}"
    base_url: "{{ env.CUSTOM_LLM_BASE_URL }}"
    supports_structured_output: false  # По умолчанию предполагаем что нет
    default_model: custom-model

# configs/graph.yaml - обновленный
models:
  default:
    provider: openai  # По умолчанию используем OpenAI
    model_name: gpt-4o-mini
    temperature: 0.1
    max_tokens: 4000
  
  nodes:
    # Узлы без structured output - можно использовать любого OpenAI-совместимого провайдера
    generating_content:
      provider: ollama  # Локальная модель для экономии
      model_name: llama3.2
      temperature: 0.2
      max_tokens: 8000
    
    synthesis_material:
      provider: groq  # Быстрый инференс
      model_name: mixtral-8x7b-32768
      temperature: 0.1
      max_tokens: 8000
    
    # Узлы со structured output - только провайдеры с поддержкой
    generating_questions:
      provider: openai  # Требует structured output
      model_name: gpt-4o-mini
      temperature: 0.3
      max_tokens: 3000
      requires_structured_output: true
    
    edit_material:
      provider: groq-tools  # Groq модель с поддержкой tools
      model_name: llama3-groq-70b-8192-tool-use-preview
      temperature: 0.2
      max_tokens: 6000
      requires_structured_output: true
    
    security_guard:
      provider: openai  # Критичный компонент - используем OpenAI
      model_name: gpt-4o-mini
      temperature: 0.0
      max_tokens: 1000
      requires_structured_output: true
```

### 4. Обновление переменных окружения

```bash
# env.example - обновленный

# API Keys для различных провайдеров (используются через Jinja2 шаблоны в providers.yaml)
OPENAI_API_KEY=your_openai_api_key
GROQ_API_KEY=your_groq_api_key
TOGETHER_API_KEY=your_together_api_key
OPENROUTER_API_KEY=your_openrouter_api_key

# Кастомный провайдер
CUSTOM_API_KEY=your_custom_api_key
CUSTOM_LLM_BASE_URL=https://your-custom-api.com/v1

# Providers configuration
PROVIDERS_CONFIG_PATH=./configs/providers.yaml
```

### 5. Загрузка конфигурации с поддержкой Jinja2

```python
# learnflow/config/config_loader.py

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

### 6. Интеграция в существующий код

```python
# learnflow/models/model_factory.py - обновление для работы с провайдерами

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
    
    _model_factory = ModelFactory(providers_config, default_api_key=api_key)
    return _model_factory
```

### 7. Обновление ConfigManager

```python
# learnflow/config/config_manager.py

from .config_loader import load_yaml_with_env

class ConfigManager:
    def __init__(self, providers_path: str = None, graph_path: str = None):
        # Загружаем конфигурации с подстановкой переменных окружения
        if providers_path:
            self.providers_config = load_yaml_with_env(providers_path)
        if graph_path:
            self.graph_config = load_yaml_with_env(graph_path)
    
    def get_providers_config(self) -> Dict[str, ProviderConfig]:
        """Возвращает конфигурацию провайдеров с уже подставленными API ключами"""
        providers = {}
        for name, config in self.providers_config.get("providers", {}).items():
            providers[name] = ProviderConfig(**config)
        return providers
```


## План миграции (Direct Migration)

### Фаза 1: Подготовка инфраструктуры
1. Создать `learnflow/config/config_loader.py` с функцией `load_yaml_with_env()`
2. Добавить зависимость Jinja2 в `pyproject.toml` (если еще нет)
3. Создать файл `configs/providers.yaml` с конфигурацией провайдеров

### Фаза 2: Обновление моделей конфигурации
1. Обновить `learnflow/config/config_models.py`:
   - Добавить класс `ProviderConfig` (без `api_version` и `extra_params`)
   - Добавить поля `provider` и `requires_structured_output` в `ModelConfig`

### Фаза 3: Обновление фабрики моделей
1. Модифицировать `learnflow/models/model_factory.py`:
   - Добавить поддержку `providers_config` в конструктор
   - Обновить метод `create_model()` для работы с `base_url`
   - Добавить валидацию `supports_structured_output`
   - Убрать логику инжекта API ключей (они уже подставлены через Jinja2)

### Фаза 4: Интеграция ConfigManager
1. Обновить `learnflow/config/config_manager.py`:
   - Использовать `load_yaml_with_env()` для загрузки конфигов
   - Добавить метод `get_providers_config()`

### Фаза 5: Конфигурация
1. Обновить `configs/graph.yaml`:
   - Добавить поле `provider` для каждого узла
   - Добавить `requires_structured_output: true` для узлов со structured output
2. Обновить `.env` с API ключами для всех используемых провайдеров

### Фаза 6: Тестирование
1. Протестировать загрузку конфигурации с Jinja2 шаблонами
2. Проверить работу узлов с разными провайдерами
3. Убедиться в корректной валидации structured output

## Ключевые преимущества упрощенного решения

1. **Простота реализации**: Используем только `ChatOpenAI` с параметром `openai_api_base`
2. **Совместимость**: Работает с любым OpenAI-совместимым API
3. **Минимальные изменения кода**: Обновляется только фабрика моделей
4. **Явная валидация**: Проверка поддержки structured output на уровне конфигурации
5. **Нет новых зависимостей**: Не требуется устанавливать дополнительные пакеты

## Потенциальные проблемы и решения

## Важные замечания

1. **OpenAI-совместимость**: Решение работает только с провайдерами, предоставляющими OpenAI-совместимый API
2. **Structured Output**: Метод `with_structured_output()` требует поддержки function calling на стороне провайдера
3. **Параметр base_url**: В LangChain используется `openai_api_base`, не `base_url`
4. **Тестирование**: Каждый новый провайдер требует тестирования, особенно для structured output

## Заключение

Упрощенная архитектура позволяет:
- Использовать любые OpenAI-совместимые провайдеры через единый интерфейс `ChatOpenAI`
- Минимально изменить существующий код (только фабрика моделей)
- Явно контролировать какие узлы требуют structured output
- Легко добавлять новые провайдеры через конфигурацию
- Избежать дополнительных зависимостей

Решение оптимально для MVP, так как обеспечивает необходимую гибкость при минимальной сложности реализации.