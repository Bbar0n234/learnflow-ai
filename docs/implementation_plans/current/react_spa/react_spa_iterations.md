## Детализация итераций для React SPA реализации

### **Итерация 1: Базовая инфраструктура и Artifacts Service**
**Цель:** Создать файловое хранилище и REST API для работы с артефактами

**Задачи:**
1. **Создание структуры Artifacts Service:**
   - `artifacts-service/` директория с FastAPI приложением
   - `artifacts-service/app/main.py` - основной FastAPI app
   - `artifacts-service/app/models.py` - Pydantic модели
   - `artifacts-service/app/storage.py` - файловые операции
   - `artifacts-service/requirements.txt` - зависимости # TODO: неправда, будет uv

2. **Реализация файлового хранилища:**
   - Создание `data/artifacts/` структуры
   - Логика создания папок по `thread_id`
   - Валидация путей и безопасность

3. **Базовые API endpoints:**
   ```python
   GET /health                    # health check
   GET /files/{thread_id}         # список файлов thread'а
   GET /files/{thread_id}/{path}  # содержимое файла
   POST /files/{thread_id}/{path} # создание/обновление файла
   DELETE /files/{thread_id}/{path} # удаление файла
   ```

4. **Docker конфигурация:**
   - `artifacts-service/Dockerfile`
   - Базовое обновление `docker-compose.yaml`

**Критерии готовности:**
- [x] Artifacts Service запускается в Docker
- [x] API endpoints работают через Postman/curl
- [x] Файлы сохраняются в правильной структуре
- [x] Валидация путей работает корректно

**✅ Итерация 1 завершена** (2025-08-06)

---

### **Итерация 2: Базовый React SPA**
**Цель:** Создать веб-интерфейс для просмотра файлов и рендеринга Markdown

**Задачи:**
1. **Инициализация Vite проекта:**
   ```bash
   npm create vite@latest web-ui -- --template react-ts
   ```
   - Настройка TypeScript конфигурации
   - Установка зависимостей: react-markdown, remark-math, rehype-katex

2. **Основные компоненты:**
   - `FileExplorer.tsx` - древовидное отображение файлов
   - `MarkdownViewer.tsx` - рендеринг Markdown с LaTeX
   - `Layout.tsx` - основной layout приложения
   - `ApiClient.ts` - HTTP клиент для Artifacts Service

3. **Базовая функциональность:**
   - Отображение списка thread'ов
   - Навигация по файлам thread'а
   - Рендеринг Markdown файлов с LaTeX формулами
   - Базовое состояние (useState/useEffect)

4. **Стилизация:**
   - Установка Tailwind CSS
   - Адаптивный дизайн
   - Темная/светлая тема

**Критерии готовности:**
- [ ] SPA открывается в браузере на localhost:3000
- [ ] Отображается список файлов из Artifacts Service
- [ ] Markdown рендерится с LaTeX формулами
- [ ] Базовая навигация работает

---

### **Итерация 3: Интеграция с LearnFlow**
**Цель:** Заменить GitHub интеграцию на сохранение в Artifacts Service

**Задачи:**
1. **Модификация LearnFlow кода:**
   - Создание `learnflow/artifacts_manager.py` вместо `github.py`
   - Обновление `ExamState` модели (замена `github_*` полей)
   - Модификация workflow nodes для сохранения в локальную FS

2. **Artifacts Manager реализация:**
   ```python
   class ArtifactsManager:
       def save_content(self, thread_id: str, filename: str, content: str)
       def create_thread_folder(self, thread_id: str)
       def save_metadata(self, thread_id: str, state: ExamState)
   ```

3. **Обновление workflow nodes:**
   - `ContentGenerationNode` → сохранение в `generated_material.md`
   - `RecognitionNode` → сохранение в `recognized_notes.md`
   - `SynthesisNode` → сохранение в `synthesized_material.md`
   - `QuestionGenerationNode` → сохранение в `gap_questions.md`
   - `AnswerGenerationNode` → сохранение в `answers/question_N.md`

4. **Обновление API endpoints:**
   - Добавление `GET /threads` для получения списка thread'ов
   - Расширение метаданных в Artifacts Service

**Критерии готовности:**
- [ ] LearnFlow workflow сохраняет файлы в `data/artifacts/`
- [ ] Web UI отображает файлы от реального workflow
- [ ] Все типы артефактов (материалы, вопросы, ответы) сохраняются
- [ ] Метаданные thread'а доступны через API

---

### **Итерация 4: Real-time функциональность**
**Цель:** Добавить WebSocket для live updates и отображение прогресса workflow

**Задачи:**
1. **WebSocket в Artifacts Service:**
   ```python
   @app.websocket("/ws/{thread_id}")
   async def websocket_endpoint(websocket: WebSocket, thread_id: str)
   ```
   - Уведомления о создании/изменении файлов
   - Отправка прогресса workflow

2. **Интеграция с LearnFlow:**
   - Добавление WebSocket клиента в `artifacts_manager.py`
   - Отправка событий при сохранении файлов
   - Передача статуса выполнения workflow nodes

3. **Frontend WebSocket интеграция:**
   - `useWebSocket.ts` hook для подключения
   - Real-time обновление списка файлов
   - Автоматическое обновление содержимого файлов

4. **UI улучшения:**
   - `WorkflowProgress.tsx` - индикатор прогресса
   - Уведомления о новых файлах
   - Статусы выполнения nodes

**Критерии готовности:**
- [ ] WebSocket соединение устанавливается при открытии thread'а
- [ ] Новые файлы появляются в UI без обновления страницы
- [ ] Отображается прогресс выполнения workflow
- [ ] Уведомления работают корректно

---

### **Итерация 5: Продвинутые UI фичи**
**Цель:** Добавить редактирование, структурирование файлов и аннотации

**Задачи:**
1. **Редактирование Markdown:**
   - `MarkdownEditor.tsx` с preview режимом
   - Автосохранение изменений
   - Синтаксическая подсветка кода
   - Live preview LaTeX формул

2. **Drag-n-Drop структурирование:**
   - Установка `@dnd-kit/core`
   - Перемещение файлов между папками
   - API endpoint `PUT /files/move`
   - Обновление файловой структуры на сервере

3. **Система аннотаций:**
   - Выделение фрагментов текста
   - Добавление комментариев к фрагментам
   - Сохранение аннотаций в metadata
   - Отображение аннотаций в UI

4. **Дополнительные фичи:**
   - Поиск по содержимому файлов
   - Экспорт в PDF (базовый)
   - История изменений файлов
   - Теги и категории для thread'ов

**Критерии готовности:**
- [ ] Inline редактирование Markdown работает с LaTeX preview
- [ ] Drag-n-drop перемещение файлов функционально
- [ ] Аннотации сохраняются и отображаются
- [ ] Поиск находит контент в файлах

---

### **Последовательность выполнения:**

1. **Итерация 1** → Создаем backend инфраструктуру
2. **Итерация 2** → Создаем frontend для просмотра
3. **Итерация 3** → Интегрируем с существующим workflow
4. **Итерация 4** → Добавляем real-time обновления
5. **Итерация 5** → Улучшаем пользовательский опыт

Каждая итерация даёт работающий результат и может быть протестирована независимо. Это позволяет получать обратную связь на каждом этапе и корректировать направление разработки.