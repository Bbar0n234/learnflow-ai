# Упрощенный план реализации UI улучшений LearnFlow AI

## Обзор
План минимальных изменений для улучшения Web UI без создания новых сервисов. Используем существующую инфраструктуру artifacts-service.

## Этап 1: Backend - Расширение модели данных (2-3 часа)

### 1.1 Добавить поле display_name в SessionMetadata
**Файл:** `artifacts-service/models.py`
```python
class SessionMetadata(BaseModel):
    session_id: str
    thread_id: str 
    input_content: str
    display_name: Optional[str] = None  # НОВОЕ ПОЛЕ - краткое название 3-5 слов
    created: datetime
    modified: datetime
    status: str = "active"
```

### 1.2 Генерация display_name в InputProcessingNode
**Файл:** `learnflow/nodes/input_processing.py`

После валидации input_content через guardrails:
```python
# Генерируем краткое название для папки
display_name_prompt = f"""
Создай краткое название (3-5 слов) для следующего экзаменационного вопроса:
"{input_content}"

Требования:
- Максимум 5 слов
- Отражает суть вопроса
- Без спецсимволов и знаков препинания
- На том же языке, что и вопрос

Ответ дай ТОЛЬКО название, без объяснений.
"""

display_name = await self.llm.ainvoke(display_name_prompt)
```

### 1.3 Сохранение display_name при создании сессии
**Файл:** `learnflow/services/artifacts_manager.py` (или где создается сессия)

При создании новой сессии передавать display_name в SessionMetadata.

## Этап 2: Frontend - Configuration System (1-2 часа)

### 2.1 Создать конфигурацию маппинга имен
**Файл:** `web-ui/src/config/names_map.json`
```json
{
  "files": {
    "generated_document.md": "Сгенерированный документ",
    "synthesized_material.md": "Синтезированный материал", 
    "final_answer.md": "Финальный ответ",
    "recognized_text.md": "Распознанный текст",
    "questions.md": "Вопросы для проверки"
  },
  "folders": {
    "answers": "Ответы на вопросы"
  },
  "patterns": {
    "answer_\\d{3}\\.md": "Ответ на вопрос {{number}}"
  }
}
```

**Примечание:** Для файлов вида `answers/answer_001.md`, `answers/answer_002.md` и т.д. (всего 5 файлов на сессию) используется pattern matching для генерации названий "Ответ на вопрос 1", "Ответ на вопрос 2" и т.д.

### 2.2 Сервис для работы с конфигурацией
**Файл:** `web-ui/src/services/ConfigService.ts`
```typescript
import namesMap from '../config/names_map.json';

export class ConfigService {
  static getDisplayName(filePath: string): string {
    // Проверяем прямое соответствие
    const filename = filePath.split('/').pop() || filePath;
    if (namesMap.files[filename]) {
      return namesMap.files[filename];
    }
    
    // Проверяем паттерны (например, answer_001.md)
    for (const [pattern, template] of Object.entries(namesMap.patterns)) {
      const regex = new RegExp(pattern);
      const match = filename.match(regex);
      if (match) {
        // Извлекаем номер из имени файла
        const numberMatch = filename.match(/\d+/);
        if (numberMatch) {
          const number = parseInt(numberMatch[0], 10);
          return template.replace('{{number}}', number.toString());
        }
      }
    }
    
    // Проверяем, находится ли файл в специальной папке
    const pathParts = filePath.split('/');
    if (pathParts.length > 1) {
      const folder = pathParts[pathParts.length - 2];
      if (namesMap.folders[folder]) {
        return `${namesMap.folders[folder]} - ${filename}`;
      }
    }
    
    // Fallback - возвращаем оригинальное имя
    return filename;
  }
  
  static deduplicateNames(names: string[]): Map<string, string> {
    const result = new Map<string, string>();
    const counts = new Map<string, number>();
    
    names.forEach(name => {
      const count = counts.get(name) || 0;
      counts.set(name, count + 1);
      
      if (count === 0) {
        result.set(name, name);
      } else {
        result.set(name, `${name} - ${count + 1}`);
      }
    });
    
    return result;
  }
}
```

## Этап 3: Frontend - Accordion Sidebar (1-2 дня)

### 3.1 Создать компонент AccordionSidebar
**Файл:** `web-ui/src/components/AccordionSidebar.tsx`

Структура компонента:
```typescript
interface AccordionSidebarProps {
  threads: Thread[];
  selectedThread: string | null;
  selectedSession: string | null;
  selectedFile: string | null;
  onSelect: (thread: string, session?: string, file?: string) => void;
}

// Иерархия:
// Thread (показываем thread_id как Telegram ID)
//   └── Session (показываем display_name или input_content)
//       ├── File (показываем user-friendly название)
//       └── Folder: answers/
//           ├── answer_001.md → "Ответ на вопрос 1"
//           ├── answer_002.md → "Ответ на вопрос 2"
//           ├── answer_003.md → "Ответ на вопрос 3"
//           ├── answer_004.md → "Ответ на вопрос 4"
//           └── answer_005.md → "Ответ на вопрос 5"
```

Ключевые особенности:
- Использовать состояние для управления раскрытыми секциями
- Сохранять состояние в localStorage
- Sticky headers для каждого уровня
- Обработка дубликатов input_content через ConfigService.deduplicateNames()

### 3.2 Исправить проблемы с высотой sidebar
**Файл:** `web-ui/src/styles/sidebar.css`
```css
.sidebar-container {
  height: calc(100vh - var(--header-height));
  overflow-y: auto;
  overflow-x: hidden;
  position: sticky;
  top: var(--header-height);
}

.sidebar-section-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--bg-elev);
  backdrop-filter: blur(8px);
}
```

### 3.3 Интеграция в Layout
**Файл:** `web-ui/src/components/Layout.tsx`

Заменить текущий sidebar на AccordionSidebar с правильной структурой данных.

## Этап 4: Frontend - UI Polish (0.5 дня)

### 4.1 Обновить типографику
**Файл:** `web-ui/src/styles/theme.css`
```css
:root {
  /* Увеличить базовые размеры */
  --text-xs: 0.8125rem;  /* 13px вместо 12px */
  --text-sm: 0.9375rem;  /* 15px вместо 14px */
  --text-base: 1.0625rem; /* 17px вместо 16px */
  --text-lg: 1.25rem;    /* 20px вместо 18px */
  
  /* Модульная сетка */
  --spacing-unit: 0.5rem; /* 8px */
  --spacing-xs: calc(var(--spacing-unit) * 0.5);  /* 4px */
  --spacing-sm: var(--spacing-unit);               /* 8px */
  --spacing-md: calc(var(--spacing-unit) * 2);     /* 16px */
  --spacing-lg: calc(var(--spacing-unit) * 3);     /* 24px */
  --spacing-xl: calc(var(--spacing-unit) * 4);     /* 32px */
}
```

### 4.2 Убрать лишние фоны у заголовков
**Файл:** `web-ui/src/components/MarkdownViewer.tsx`

Проверить стили для h1-h6, убрать background-color где не нужно.

## Этап 5: Интеграция и тестирование (0.5 дня)

### 5.1 Проверить flow данных
1. InputProcessingNode генерирует display_name
2. display_name сохраняется в SessionMetadata
3. Frontend получает display_name через API
4. AccordionSidebar правильно отображает иерархию
5. Маппинг файлов работает с fallback

### 5.2 Edge cases
- Пустой display_name → использовать input_content
- Дубликаты input_content → автоматическая нумерация
- Очень длинные названия → обрезка с троеточием
- Отсутствие сессий → показать placeholder

## Миграция существующих данных

### Опция 1: Lazy migration
При первом обращении к сессии без display_name:
1. Проверить наличие display_name
2. Если нет - сгенерировать из input_content
3. Сохранить в metadata

### Опция 2: Background job
Скрипт миграции:
```python
# scripts/migrate_display_names.py
for thread in get_all_threads():
    for session in thread.sessions:
        if not session.display_name and session.input_content:
            session.display_name = generate_display_name(session.input_content)
            save_session_metadata(session)
```

### Опция 3: Quick Test Migration (для тестирования UI)
**Файл:** `scripts/test_ui_migration.py`

Быстрый скрипт для подготовки существующих данных к тестированию нового UI:
```python
#!/usr/bin/env python3
"""
Скрипт для быстрой адаптации существующих сессий под новый UI.
Использовать для тестирования UI без полного прогона workflow.
"""

import json
from pathlib import Path
from datetime import datetime

# Путь к данным artifacts
DATA_PATH = Path("data/artifacts")

# Примерные display_names для тестирования
TEST_DISPLAY_NAMES = {
    "979557959": {
        "session-20250812_194751-bb111996": "RSA шифрование основы",
        "session-20250818_095712-bb111996": "Эллиптические кривые криптография"
    }
}

def update_session_metadata(thread_id: str, session_id: str):
    """Обновляет metadata сессии, добавляя display_name."""
    session_path = DATA_PATH / thread_id / "sessions" / session_id
    metadata_path = session_path / "session_metadata.json"
    
    # Читаем существующую metadata или создаем новую
    if metadata_path.exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    else:
        # Создаем базовую metadata
        metadata = {
            "session_id": session_id,
            "thread_id": thread_id,
            "input_content": "Тестовый экзаменационный вопрос",
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "status": "active"
        }
    
    # Добавляем display_name если его нет
    if "display_name" not in metadata:
        # Берем из тестовых данных или генерируем простой
        if thread_id in TEST_DISPLAY_NAMES and session_id in TEST_DISPLAY_NAMES[thread_id]:
            metadata["display_name"] = TEST_DISPLAY_NAMES[thread_id][session_id]
        else:
            # Простая генерация из session_id
            metadata["display_name"] = f"Сессия {session_id[:8]}"
    
    # Сохраняем обновленную metadata
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Updated {thread_id}/{session_id}: {metadata.get('display_name')}")

def main():
    """Обновляет все существующие сессии."""
    if not DATA_PATH.exists():
        print(f"Data path {DATA_PATH} not found!")
        return
    
    # Проходим по всем threads
    for thread_dir in DATA_PATH.iterdir():
        if not thread_dir.is_dir():
            continue
            
        thread_id = thread_dir.name
        sessions_dir = thread_dir / "sessions"
        
        if not sessions_dir.exists():
            continue
        
        # Проходим по всем сессиям
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
                
            session_id = session_dir.name
            update_session_metadata(thread_id, session_id)
    
    print("\n✅ Migration completed! You can now test the new UI.")

if __name__ == "__main__":
    main()
```

**Использование:**
```bash
# Запустить перед тестированием UI
python scripts/test_ui_migration.py

# Затем запустить web-ui для проверки
cd web-ui && npm run dev
```

Этот скрипт:
- Добавит display_name к существующим сессиям
- Создаст session_metadata.json если его нет
- Позволит сразу протестировать новый accordion UI без запуска полного workflow

## Итоговая оценка времени

| Этап | Время |
|------|-------|
| Backend - модель данных | 2-3 часа |
| Frontend - конфигурация | 1-2 часа |
| Frontend - Accordion sidebar | 1-2 дня |
| Frontend - UI polish | 0.5 дня |
| Интеграция и тестирование | 0.5 дня |
| **ИТОГО** | **3-4 дня** |

## Преимущества подхода

1. **Минимальные изменения backend** - только добавление одного поля и генерация display_name
2. **Никаких новых сервисов** - используем существующий artifacts-service
3. **Постепенная миграция** - старые данные продолжают работать
4. **Простая конфигурация** - JSON файл для маппинга без пересборки контейнера
5. **Переиспользование кода** - максимально используем существующие компоненты