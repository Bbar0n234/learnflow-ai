## Высокоуровневый план реализации React SPA для LearnFlow AI

### 1. **Архитектурные изменения**

**Текущее состояние:**
- GitHub интеграция (`learnflow/github.py`) для сохранения артефактов
- ExamState содержит `github_folder_path`, `github_learning_material_url`
- Артефакты сохраняются в виде markdown файлов в GitHub

**Целевое состояние:**
- Локальная файловая система для артефактов (Docker volume)
- Новый Artifacts Service (FastAPI) для управления файлами
- React SPA с Vite для отображения и редактирования
- WebSocket real-time обновления между workflow и UI

### 2. **Backend: Artifacts Service (FastAPI)**

**Структура:** `artifacts-service/`
- **API endpoints:**
  - `GET /files` - получение иерархии файлов и папок
  - `GET /files/{path}` - чтение содержимого файла
  - `POST /files/{path}` - создание/обновление файла
  - `PUT /files/move` - перемещение файлов (drag-n-drop)
  - `DELETE /files/{path}` - удаление файлов
  - `GET /metadata/{thread_id}` - получение метаданных из ExamState
  
- **WebSocket endpoint:**
  - `WS /ws/{thread_id}` - real-time обновления при изменениях в workflow

- **Интеграция с ExamState:**
  - Подключение к той же PostgreSQL БД
  - Получение метаданных workflow для связи файлов с процессом

### 3. **Frontend: React SPA с Vite**

**Структура:** `web-ui/`
- **Технологический стек:**
  - Vite + React 18 + TypeScript
  - react-markdown + remark-math + rehype-katex (LaTeX рендеринг)
  - @dnd-kit/core (drag-n-drop для структурирования файлов)
  - Socket.io-client (WebSocket для real-time обновлений)
  - Tailwind CSS (современный UI)

- **Основные компоненты:**
  - `FileTree` - иерархия файлов с drag-n-drop
  - `MarkdownEditor` - редактор с preview LaTeX формул
  - `WorkflowProgress` - визуализация статуса LangGraph nodes
  - `CommentsPanel` - аннотации к фрагментам текста

### 4. **Модификации существующего LearnFlow workflow**

**Изменения в learnflow/:**
- **Замена `github.py` на `artifacts_manager.py`:**
  - Сохранение файлов в локальную файловую систему
  - Отправка WebSocket уведомлений при создании новых артефактов
  
- **Обновление ExamState:**
  - Замена `github_*` полей на `artifacts_*`
  - Добавление `artifacts_folder_path`, `artifacts_files_map`
  
- **Модификация workflow nodes:**
  - Каждый node после генерации контента сохраняет результат через artifacts_manager
  - Отправка WebSocket событий о прогрессе

### 5. **Файловая система артефактов**

**Структура хранения:** `data/artifacts/{thread_id}/`
```
thread_id/
├── exam_question.md
├── generated_material.md
├── recognized_notes.md
├── synthesized_material.md
├── gap_questions.md
└── answers/
    ├── question_01.md
    ├── question_02.md
    └── ...
```

**Метаданные:** `thread_id/metadata.json`
- Связь с ExamState
- Timestamps создания/изменения
- Структура папок и тегов

### 6. **Docker Compose обновления**

**Новые сервисы:**
```yaml
services:
  artifacts-service:
    build: ./artifacts-service
    ports: ["8001:8000"]
    volumes: ["./data/artifacts:/app/artifacts"]
    
  web-ui:
    build: ./web-ui
    ports: ["3000:3000"]
    environment: ["VITE_API_URL=http://artifacts-service:8000"]
```

**Shared volumes:**
- `./data/artifacts` монтируется в learnflow, artifacts-service

### 7. **Этапы реализации (MVP → Full)**

**MVP Phase (базовая функциональность):**
1. Artifacts Service с базовым CRUD API
2. React SPA с отображением файлов и Markdown рендерингом
3. Замена GitHub интеграции на локальное сохранение
4. Docker Compose с тремя сервисами

**Phase 2 (продвинутые фичи):**
1. WebSocket real-time обновления
2. Drag-n-drop структурирование файлов
3. Inline редактирование Markdown с LaTeX preview
4. Комментарии и аннотации

**Phase 3 (расширения):**
1. Версионность файлов
2. Export в PDF с LaTeX
3. AI-ассистированное редактирование
4. Collaborative editing

### 8. **Ключевые технические решения**

- **API-first подход:** React SPA взаимодействует с файлами только через Artifacts Service API
- **Сохранение совместимости:** ExamState структура адаптируется с минимальными изменениями
- **Real-time sync:** WebSocket обеспечивает мгновенное отображение изменений от workflow
- **Микросервисная архитектура:** Каждый компонент (LearnFlow, Artifacts, UI) может развиваться независимо

Этот план сохраняет всю существующую функциональность LearnFlow AI, но заменяет GitHub интеграцию на современную локальную веб-платформу с возможностями real-time редактирования и структурирования учебных материалов.