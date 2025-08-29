# FEAT-EXPORT-601: Markdown и PDF экспорт заметок

## Архитектурное предложение по реализации функционала экспорта

### 1. Обзор текущей архитектуры

#### 1.1 Ключевые компоненты системы
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Telegram Bot  │────▶│  FastAPI Service │────▶│ LangGraph Flow  │
│   (port: N/A)   │     │   (port: 8000)   │     │   (workflow)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                         │
         │                       ▼                         ▼
         │              ┌──────────────────┐     ┌─────────────────┐
         └─────────────▶│ Artifacts Service│────▶│  File Storage   │
                        │   (port: 8001)   │     │ /data/artifacts │
                        └──────────────────┘     └─────────────────┘
                                 ▲
                                 │
                        ┌──────────────────┐
                        │     Web UI       │
                        │   (port: 3001)   │
                        └──────────────────┘
```

#### 1.2 Текущая структура хранения контента
```
data/artifacts/{thread_id}/sessions/{session_id}/
├── session_metadata.json       # Метаданные сессии
├── generated_material.md       # Сгенерированный материал
├── recognized_notes.md         # Распознанные рукописные заметки
├── synthesized_material.md     # Синтезированный материал
├── questions.md            # Вопросы для gap-анализа
└── answers/
    ├── answer_001.md
    ├── answer_002.md
    └── ...
```

### 2. Бизнес-требования и функциональность

#### 2.1 Поддерживаемые форматы экспорта
- **Markdown** (.md) - исходный формат документов
- **PDF** (.pdf) - для печати и офлайн-чтения
- Другие форматы (DOCX, HTML) не требуются

#### 2.2 Варианты экспорта

##### 2.2.1 Экспорт одного документа
- Любой отдельный файл из текущей или исторических сессий
- Экспортируется как одиночный файл в выбранном формате (MD/PDF)
- Доступные документы:
  - `generated_material.md` - первичная генерация
  - `recognized_notes.md` - распознанные заметки
  - `synthesized_material.md` - финальный материал
  - `questions.md` - вопросы для закрепления
  - `answers/answer_XXX.md` - отдельные ответы

##### 2.2.2 Экспорт пакета документов
- Всегда экспортируется как **ZIP-архив** с отдельными файлами
- Два режима пакета:
  - **"Финальные документы"** (по умолчанию):
    - `synthesized_material.md`
    - `questions.md`
    - Все файлы из `answers/`
  - **"Все документы"**:
    - Включает также промежуточные: `generated_material.md`, `recognized_notes.md`
    - Плюс все финальные документы

#### 2.3 Пользовательские настройки

Каждый пользователь может настроить:
1. **Режим пакета по умолчанию**: финальные / все документы
2. **Формат экспорта по умолчанию**: Markdown / PDF

Эти настройки сохраняются для каждого пользователя и применяются при быстром экспорте.

#### 2.4 Работа с историческими сессиями
- Показываются **последние 5 сессий** (без пагинации)
- Формат отображения: `"[Первые 30 символов вопроса...] - [Дата DD.MM.YYYY]"`
- Пример: `"Объясните принцип работы нейр... - 26.08.2025"`
- Из истории доступны те же опции экспорта, что и для текущей сессии

#### 2.5 Пользовательские сценарии

##### Сценарий 1: Быстрый экспорт текущей сессии
1. Пользователь вводит `/export`
2. Система использует настройки по умолчанию
3. Генерируется и отправляется файл/архив

##### Сценарий 2: Экспорт с выбором параметров
1. Пользователь выбирает экспорт через меню
2. Выбирает: документ/пакет, формат
3. Получает результат

##### Сценарий 3: Экспорт исторической сессии
1. Запрашивает `/sessions` или `/history`
2. Выбирает сессию из списка
3. Выбирает параметры экспорта
4. Получает результат

### 3. Предлагаемая архитектура экспорта

#### 3.1 Основная точка интеграции: Artifacts Service

**Обоснование выбора:**
- Уже имеет полный доступ ко всем данным сессий
- Реализована безопасность и валидация
- RESTful архитектура позволяет легко добавить новые эндпоинты
- Может обслуживать множественных клиентов (Web UI, Bot, API)
- Архитектурно позиционирован как слой данных

#### 3.2 Архитектурная схема с экспортом
```
┌──────────────────────────────────────────────────────────────┐
│                    EXPORT ARCHITECTURE                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐        ┌─────────────────────────┐         │
│  │ Telegram Bot│───────▶│   Export Commands:      │         │
│  └─────────────┘        │   /export              │         │
│                         │   /sessions (history)   │         │
│                         └──────────┬──────────────┘         │
│                                    │                         │
│  ┌─────────────┐        ┌─────────▼──────────────┐         │
│  │   Web UI    │───────▶│  Artifacts Service     │         │
│  └─────────────┘        │  Extended API:         │         │
│         │               │                        │         │
│         ▼               │  GET /export/single    │         │
│  ┌─────────────────┐    │  GET /export/package  │         │
│  │ Export Dialog   │    │  GET /export/history  │         │
│  │ Export Buttons  │    │  GET /user/settings   │         │
│  └─────────────────┘    └─────────┬──────────────┘         │
│                                    │                         │
│                         ┌──────────▼──────────────┐         │
│                         │   Export Engine        │         │
│                         ├───────────────────────┤         │
│                         │ • Markdown Processor   │         │
│                         │ • PDF Generator        │         │
│                         │ • ZIP Archiver        │         │
│                         │ • Template Engine      │         │
│                         └───────────────────────┘         │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### 4. Детальный план реализации

#### 4.1 Расширение Artifacts Service

##### 4.1.1 Новые API эндпоинты
```python
# artifacts-service/main.py

@app.get("/threads/{thread_id}/sessions/{session_id}/export/single")
async def export_single_document(
    thread_id: str,
    session_id: str,
    document_name: str,  # e.g., "synthesized_material", "questions"
    format: ExportFormat = Query(ExportFormat.MARKDOWN)
) -> FileResponse:
    """Экспорт одного документа"""
    pass

@app.get("/threads/{thread_id}/sessions/{session_id}/export/package")
async def export_package(
    thread_id: str,
    session_id: str,
    package_type: PackageType = Query(PackageType.FINAL),  # FINAL or ALL
    format: ExportFormat = Query(ExportFormat.MARKDOWN)
) -> FileResponse:
    """Экспорт пакета документов в ZIP архиве"""
    pass

@app.get("/users/{user_id}/sessions/recent")
async def get_recent_sessions(
    user_id: str,
    limit: int = Query(5, max=5)
) -> List[SessionSummary]:
    """Получение списка последних сессий для экспорта"""
    pass

@app.get("/users/{user_id}/export-settings")
async def get_export_settings(user_id: str) -> ExportSettings:
    """Получение настроек экспорта пользователя"""
    pass

@app.put("/users/{user_id}/export-settings")
async def update_export_settings(
    user_id: str,
    settings: ExportSettings
) -> ExportSettings:
    """Обновление настроек экспорта пользователя"""
    pass
```

##### 4.1.2 Компоненты Export Engine
```python
# artifacts-service/services/export/

├── base.py              # Базовый класс ExportEngine
├── markdown_export.py   # MarkdownExporter
├── pdf_export.py       # PDFExporter (использует markdown-pdf или weasyprint)
├── zip_export.py       # ZIPExporter для создания архивов
├── templates/          # Шаблоны для экспорта
│   ├── session_template.md
│   ├── thread_template.md
│   └── styles.css      # Стили для PDF
└── utils.py           # Вспомогательные функции
```

##### 4.1.3 Модели данных
```python
# artifacts-service/models.py

class ExportFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"

class PackageType(str, Enum):
    FINAL = "final"  # Только финальные документы
    ALL = "all"      # Все документы включая промежуточные

class ExportSettings(BaseModel):
    default_format: ExportFormat = ExportFormat.MARKDOWN
    default_package_type: PackageType = PackageType.FINAL
    user_id: str
    
class SessionSummary(BaseModel):
    thread_id: str
    session_id: str
    created_at: datetime
    question_preview: str  # Первые 30 символов вопроса
    display_name: str  # Форматированное имя для отображения
```

#### 4.2 Интеграция с Web UI

##### 4.2.1 Новые компоненты React
```typescript
// web-ui/src/components/export/

├── ExportDialog.tsx      // Диалог выбора параметров экспорта
├── ExportButton.tsx      // Кнопка экспорта
├── ExportProgress.tsx    // Индикатор прогресса
└── ExportPreview.tsx     // Предпросмотр перед экспортом
```

##### 4.2.2 Расширение API Client
```typescript
// web-ui/src/services/ApiClient.ts

class ApiClient {
  // Существующие методы...
  
  async exportSession(
    threadId: string,
    sessionId: string,
    options: ExportOptions
  ): Promise<Blob> {
    const response = await fetch(
      `/api/threads/${threadId}/sessions/${sessionId}/export?${params}`
    );
    return response.blob();
  }
  
  async exportThread(
    threadId: string,
    options: ExportOptions
  ): Promise<Blob> {
    // Реализация...
  }
}
```

##### 4.2.3 UI интеграция
```typescript
// Добавление кнопок экспорта в существующие компоненты:

// SessionsList.tsx - кнопка экспорта для каждой сессии
// FileExplorer.tsx - общая кнопка экспорта
// DocumentHeader.tsx - экспорт текущего документа
```

#### 4.3 Интеграция с Telegram Bot

##### 4.3.1 Новые команды бота
```python
# bot/handlers/export_handlers.py

@router.message(Command("export"))
async def export_current_session(message: Message, state: FSMContext):
    """Быстрый экспорт текущей сессии с настройками по умолчанию"""
    # 1. Получить user_id и thread_id из state
    # 2. Загрузить настройки пользователя из Artifacts Service
    # 3. Выполнить экспорт согласно настройкам
    # 4. Отправить ZIP архив или файл пользователю
    pass

@router.message(Command("export"))  # С параметрами
async def export_with_options(message: Message, state: FSMContext):
    """Экспорт с выбором параметров"""
    # Показать inline keyboard с опциями:
    # - Что экспортировать (документ/пакет)
    # - Формат (MD/PDF)
    pass

@router.message(Command("sessions"))
@router.message(Command("history"))
async def show_session_history(message: Message, state: FSMContext):
    """Показать последние 5 сессий для экспорта"""
    # 1. Запросить список последних сессий
    # 2. Отобразить inline keyboard со списком
    # 3. При выборе - показать опции экспорта
    pass

@router.message(Command("export_settings"))
async def configure_export(message: Message, state: FSMContext):
    """Настройка параметров экспорта по умолчанию"""
    # Показать текущие настройки и опции изменения
    pass
```

##### 4.3.2 Inline клавиатуры
```python
# bot/keyboards/export_keyboards.py

def get_export_options_keyboard() -> InlineKeyboardMarkup:
    """Основное меню экспорта"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Пакет (финальные)", callback_data="export:package:final"),
            InlineKeyboardButton(text="📦 Пакет (все)", callback_data="export:package:all")
        ],
        [
            InlineKeyboardButton(text="📄 Один документ", callback_data="export:single")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="export:settings")
        ]
    ])

def get_format_keyboard() -> InlineKeyboardMarkup:
    """Выбор формата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Markdown", callback_data="format:md"),
            InlineKeyboardButton(text="📄 PDF", callback_data="format:pdf")
        ]
    ])

def get_sessions_keyboard(sessions: List[SessionSummary]) -> InlineKeyboardMarkup:
    """Список последних сессий"""
    keyboard = []
    for session in sessions[:5]:
        keyboard.append([
            InlineKeyboardButton(
                text=session.display_name,
                callback_data=f"session:{session.session_id}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
```

### 5. Технологический стек для экспорта

#### 5.1 Библиотеки для генерации документов

**Markdown → PDF:**
- **markdown-pdf** - простая конвертация через CLI
- **weasyprint** - продвинутая генерация с CSS стилями
- **reportlab** - программная генерация PDF

**Создание ZIP архивов:**
- **zipfile** (встроенная библиотека Python) - для создания архивов
- **pathlib** - для работы с путями файлов

**Шаблонизация:**
- **Jinja2** - для генерации структурированного контента
- Встроенные Python f-strings для простых случаев

#### 5.2 Структура экспортируемых файлов

##### 5.2.1 Структура ZIP архива при экспорте пакета

```
session_[YYYYMMDD_HHMMSS]_export.zip
├── synthesized_material.md (или .pdf)
├── questions.md (или .pdf)
├── answers/
│   ├── answer_001.md (или .pdf)
│   ├── answer_002.md (или .pdf)
│   └── ...
└── [если выбран режим "все документы"]
    ├── generated_material.md (или .pdf)
    └── recognized_notes.md (или .pdf)
```

##### 5.2.2 Именование файлов
- Одиночный документ: `{document_name}_{session_id}.{ext}`
  - Пример: `synthesized_material_20250826_143022.pdf`
- ZIP архив: `session_{session_id}_export.zip`
  - Пример: `session_20250826_143022_export.zip`

### 6. Поэтапная реализация

#### Этап 1: Пользовательские настройки и модели (1 день)
1. Создать модели ExportSettings, SessionSummary
2. Реализовать хранение настроек пользователей
3. API для управления настройками

#### Этап 2: Базовый экспорт в Markdown (1-2 дня)
1. Создать базовый ExportEngine в Artifacts Service
2. Реализовать экспорт одиночных документов
3. Реализовать создание ZIP архивов для пакетов
4. API эндпоинты для экспорта
5. Протестировать с существующими данными

#### Этап 3: PDF генерация (2 дня)
1. Интегрировать weasyprint или markdown-pdf
2. Создать CSS стили для PDF
3. Реализовать PDFExporter
4. Добавить обработку изображений

#### Этап 4: История сессий (1 день)
1. API для получения последних 5 сессий
2. Форматирование отображаемых имен
3. Интеграция с экспортом

#### Этап 5: Telegram Bot интеграция (2 дня)
1. Команда `/export` для быстрого экспорта
2. Команды `/sessions` и `/history`
3. Inline клавиатуры для выбора опций
4. Команда `/export_settings`
5. Обработка callback запросов
6. Отправка файлов и архивов

#### Этап 6: Web UI интеграция (2 дня)
1. Создать компоненты ExportDialog и ExportButton
2. Интегрировать в существующие компоненты
3. Расширить ApiClient
4. Добавить управление настройками

#### Этап 7: Оптимизация и тестирование (1 день)
1. Оптимизация генерации больших архивов
2. Тестирование всех сценариев
3. Обработка ошибок
4. Документация

### 7. Преимущества предлагаемого решения

1. **Централизованность**: Вся логика экспорта в одном сервисе
2. **Масштабируемость**: Легко добавлять новые форматы
3. **Переиспользование**: Один API для всех клиентов
4. **Консистентность**: Единообразный экспорт везде
5. **Безопасность**: Валидация и контроль доступа в одном месте
6. **Производительность**: Возможность кеширования и оптимизации

### 8. Альтернативные подходы (не рекомендуются)

#### 8.1 Реализация в FastAPI Service
- ❌ Дублирование логики работы с файлами
- ❌ Нарушение принципа единой ответственности
- ❌ Усложнение основного workflow

#### 8.2 Отдельный Export Service
- ❌ Избыточная сложность архитектуры
- ❌ Дополнительная точка отказа
- ❌ Необходимость дублирования доступа к файлам

#### 8.3 Клиентская генерация (в браузере/боте)
- ❌ Сложность реализации PDF в браузере
- ❌ Ограничения Telegram Bot API
- ❌ Дублирование логики

### 9. Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Большой объем данных при экспорте | Средняя | Высокое | Streaming, ограничение на 5 сессий |
| Проблемы с кириллицей в PDF | Высокая | Среднее | Правильная настройка шрифтов |
| Timeout при генерации ZIP | Низкая | Среднее | Асинхронная обработка |
| Потеря настроек пользователя | Низкая | Низкое | Персистентное хранение в БД |

### 10. Метрики успеха

1. **Технические метрики:**
   - Время генерации экспорта < 5 сек для типичной сессии
   - Поддержка 2 форматов (MD, PDF)
   - Zero-downtime deployment

2. **Пользовательские метрики:**
   - Использование функции экспорта > 30% активных пользователей
   - Успешная генерация > 95% запросов
   - Удовлетворенность качеством экспорта > 4.5/5

### 11. Заключение

Предлагаемая архитектура обеспечивает:
- ✅ Минимальные изменения в существующем коде
- ✅ Централизованное управление экспортом
- ✅ Поддержку множественных форматов
- ✅ Единообразный опыт для всех интерфейсов
- ✅ Простоту расширения и поддержки

**Рекомендуемый порядок реализации:**
1. Пользовательские настройки и модели данных
2. Базовый экспорт в Markdown + ZIP архивы
3. PDF генерация
4. История сессий
5. Telegram Bot интеграция
6. Web UI интеграция
7. Оптимизация и тестирование

**Общее время реализации:** 9-10 дней при работе одного разработчика.

### 12. Итоговая бизнес-логика

**Ключевые принципы:**
1. **Простота использования**: Команда `/export` работает мгновенно с настройками по умолчанию
2. **Гибкость**: Пользователь может экспортировать как отдельные документы, так и пакеты
3. **Персонализация**: Каждый пользователь настраивает свои предпочтения один раз
4. **Доступность истории**: Последние 5 сессий всегда доступны для экспорта
5. **Универсальность**: Единая логика для Telegram Bot и Web UI

**Форматы экспорта:**
- Markdown (.md) - для редактирования и дальнейшей работы
- PDF (.pdf) - для печати и офлайн-чтения
- ZIP архивы - для пакетного экспорта нескольких документов

**Пользовательский опыт:**
- Быстрый экспорт одной командой
- Интуитивная навигация по истории сессий
- Понятные настройки без избыточности
- Предсказуемое поведение системы