# Implementation Plan: Replace Local File Paths with Web UI URLs

## Смысл и цель задачи

Заменить локальные пути файлов артефактов на Web UI URLs для улучшения пользовательского опыта. Вместо отображения технических путей вида `/data/artifacts/user_123/session_456/` пользователи будут получать кликабельные ссылки на веб-интерфейс с роутингом и навигацией.

## Архитектура решения

Основные компоненты для модификации:
- **GraphManager** (`learnflow/core/graph_manager.py`) - центральный менеджер workflow, будет генерировать Web UI URLs вместо локальных путей
- **Settings** (`learnflow/config/settings.py`) - добавить настройку WEB_UI_URL
- **LocalArtifactsManager** (`learnflow/services/artifacts_manager.py`) - удалить избыточный метод push_complete_materials
- **ProcessResponse** в API (`learnflow/api/main.py`) - убедиться в правильной передаче URL
- **Telegram Bot** (`bot/main.py`) - корректная обработка URL в сообщениях

Новые структуры данных:
- Расширение словаря `artifacts_data` в GraphManager для хранения URL и их статусов
- Механизм отслеживания отправленных/неотправленных URL

## Полный flow работы функционала

1. **Инициализация сессии** - при создании новой сессии через `push_learning_material`:
   - Генерируется session_id
   - Создается запись в artifacts_data с базовым URL веб-интерфейса
   - Инициализируются словари pending_urls и sent_urls

2. **Сохранение артефактов** - для каждого узла workflow:
   - Узел сохраняет артефакт через LocalArtifactsManager
   - GraphManager генерирует Web UI URL для файла
   - URL добавляется в pending_urls с меткой и описанием
   - При прерывании workflow pending_urls отправляются пользователю

3. **Отправка URL пользователю**:
   - При прерывании (interrupt) - отправляются только pending_urls
   - После отправки URL перемещаются из pending в sent
   - При завершении workflow - отправляется общая ссылка на сессию

4. **Обработка редактирования**:
   - При редактировании материала (edit_material) URL обновляется
   - Версионирование через timestamp или счетчик версий
   - Отправка обновленного URL пользователю

## API и интерфейсы

### GraphManager методы модификации:

**_generate_web_ui_url**
- Генерирует URL для конкретного файла
- Параметры: thread_id, session_id, file_name
- Возвращает: полный URL вида `http://localhost:5173/thread/{thread_id}/session/{session_id}/file/{file_name}`

**_track_artifact_url**
- Добавляет URL в pending_urls
- Параметры: thread_id, artifact_type, url, label
- Обновляет artifacts_data[thread_id]

**_get_pending_urls**
- Получает список неотправленных URL
- Параметры: thread_id
- Возвращает: список URL с метками для отправки

**_mark_urls_as_sent**
- Перемещает URL из pending в sent
- Параметры: thread_id, artifact_types (список)
- Предотвращает дублирование

### Settings расширение:

**web_ui_base_url**
- Конфигурируемый базовый URL веб-интерфейса
- По умолчанию: `http://localhost:5173`
- Переменная окружения: WEB_UI_BASE_URL

## Взаимодействие компонентов

```
Workflow Node -> LocalArtifactsManager -> Сохранение файла
                                       -> Возврат пути
                                       
GraphManager -> Получение пути от manager
             -> Генерация Web UI URL
             -> Добавление в pending_urls
             -> При interrupt: отправка pending URLs -> Telegram Bot
             -> Перемещение в sent_urls
```

## Порядок реализации

1. **Добавить настройку WEB_UI_BASE_URL в Settings**
   - Переменная окружения с fallback на localhost:5173
   - Валидация URL формата

2. **Расширить artifacts_data структуру в GraphManager**
   - Добавить pending_urls и sent_urls словари
   - Инициализировать при создании сессии

3. **Реализовать методы генерации и трекинга URL**
   - _generate_web_ui_url для построения URL
   - _track_artifact_url для добавления в pending
   - _get_pending_urls и _mark_urls_as_sent для управления

4. **Модифицировать методы сохранения артефактов**
   - После сохранения файла генерировать URL
   - Добавлять URL в pending_urls
   - Удалить дублирование в push_complete_materials

5. **Обновить _finalize_workflow**
   - При прерывании отправлять pending_urls
   - При завершении отправлять session URL
   - Очищать pending после отправки

6. **Протестировать с Telegram ботом**
   - Проверить корректность отображения URL
   - Валидация переходов по ссылкам
   - Обработка множественных артефактов

## Критичные граничные случаи

1. **Повторная отправка после редактирования**
   - Если synthesized_material был отредактирован, URL должен обновиться
   - Отслеживать версии через timestamp или счетчик

2. **Множественные прерывания workflow**
   - Не отправлять уже отправленные URL повторно
   - Корректно обрабатывать накопление pending_urls

3. **Параллельные сессии одного пользователя**
   - Изоляция artifacts_data по thread_id
   - Корректная очистка при delete_thread

4. **Отсутствие Web UI сервиса**
   - Генерировать URL даже если сервис недоступен
   - URL будут работать когда сервис запустится

## Конфигурационные изменения

### Переменные окружения (.env):
```
WEB_UI_BASE_URL=http://localhost:5173  # Для локальной разработки
# WEB_UI_BASE_URL=https://learnflow.example.com  # Для продакшена
```

### Docker Compose обновление:
- Добавить WEB_UI_BASE_URL в environment секцию сервисов
- Убедиться в доступности Web UI на указанном URL

## Direct Migration Strategy

Проект находится на стадии MVP, поэтому:
- **Никакого backward compatibility** - полностью заменяем локальные пути на Web UI URLs
- **Удаляем весь устаревший код** - включая push_complete_materials и переменные local_folder_path/local_session_path
- **Никаких feature flags** - прямая миграция без возможности отката
- **Минимальное тестирование** - только базовая проверка работоспособности через ручное тестирование

## Что удаляем полностью

1. **Метод push_complete_materials** в LocalArtifactsManager - избыточный
2. **Переменные local_folder_path и local_session_path** - заменяются на web_ui_urls
3. **Логику возврата локальных путей** в GraphManager
4. **Любые упоминания файловых путей в сообщениях** пользователю

## Финальная проверка

После реализации провести минимальную ручную проверку:
1. Отправить запрос через Telegram бота
2. Убедиться что приходят Web UI URLs вместо путей
3. Проверить что ссылки кликабельны и ведут на правильные страницы
4. Проверить авторизацию через /web_auth команду