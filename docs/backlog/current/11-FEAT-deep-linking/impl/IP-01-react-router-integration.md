# Implementation Plan: React Router Deep Linking Integration

## Смысл и цель задачи

Добавление поддержки deep linking через React Router в web-ui приложение LearnFlow AI для обеспечения прямой навигации к конкретным threads, sessions и файлам через URL. Это позволит пользователям делиться ссылками на конкретные материалы и использовать браузерную навигацию (кнопки назад/вперед) для перемещения по приложению.

## Архитектура решения

### Компоненты и модули
- **RouterWrapper** (`src/RouterWrapper.tsx`) - обертка с BrowserRouter и маршрутами
- **AppWithRouter** (`src/AppWithRouter.tsx`) - модифицированный App компонент с поддержкой роутинга
- **RouteGuard** (`src/components/RouteGuard.tsx`) - компонент для валидации маршрутов
- **useNavigation** (`src/hooks/useNavigation.ts`) - хук для навигации и синхронизации состояния
- **useRouteSync** (`src/hooks/useRouteSync.ts`) - хук для синхронизации URL с состоянием компонентов

### Структура маршрутов
```
/                                    - Главная страница
/thread/:threadId                    - Просмотр thread
/thread/:threadId/session/:sessionId - Просмотр session
/thread/:threadId/session/:sessionId/file/* - Просмотр файла
```

## Полный flow работы функционала

1. **Инициализация при загрузке страницы**:
   - BrowserRouter оборачивает приложение
   - Routes определяет маршруты для каждого уровня навигации
   - При прямом доступе к URL извлекаются параметры маршрута
   - Загружаются соответствующие данные через API

2. **Навигация через sidebar**:
   - Клик по элементу в AccordionSidebar вызывает handleSelect
   - handleSelect обновляет состояние и вызывает navigate() для изменения URL
   - URL синхронизируется с выбранными элементами
   - История браузера обновляется

3. **Навигация через браузер (назад/вперед)**:
   - React Router отслеживает изменения URL
   - useParams извлекает параметры из нового URL
   - Компоненты реагируют на изменения параметров через useEffect
   - Состояние приложения синхронизируется с URL
   - Sidebar автоматически раскрывается до нужного элемента

4. **Обработка невалидных URL**:
   - RouteGuard проверяет существование thread/session/file
   - При отсутствии данных происходит редирект на главную
   - Показывается сообщение об ошибке

## API и интерфейсы

### useNavigation hook
- **navigateToThread(threadId)** - переход к thread
- **navigateToSession(threadId, sessionId)** - переход к session  
- **navigateToFile(threadId, sessionId, filePath)** - переход к файлу
- **navigateHome()** - возврат на главную
- **getCurrentRoute()** - получение текущих параметров маршрута

### useRouteSync hook
- **syncUrlToState(params)** - синхронизация URL параметров с состоянием
- **syncStateToUrl(state)** - синхронизация состояния с URL
- **isValidRoute(params)** - проверка валидности маршрута

### RouteGuard component props
- **threadId** - ID thread для проверки
- **sessionId** - ID session для проверки (опционально)
- **filePath** - путь к файлу для проверки (опционально)
- **fallbackPath** - путь для редиректа при ошибке
- **children** - контент для отображения при валидном маршруте

## Взаимодействие компонентов

```
URL изменение -> React Router -> useParams -> AppWithRouter -> State Update -> AccordionSidebar
                                                     |
                                                     v
                                                API calls -> Content Loading

Sidebar Click -> handleSelect -> navigate() -> URL Update -> React Router -> State Sync
```

## Порядок реализации

1. **Базовая настройка роутинга**
   - Создание RouterWrapper с BrowserRouter и Routes
   - Определение маршрутов для всех уровней навигации
   - Обертка App компонента в роутер

2. **Интеграция с существующей навигацией**
   - Модификация handleSelect для использования navigate
   - Добавление useParams в App для извлечения параметров
   - Синхронизация параметров URL с состоянием компонента

3. **Автоматическое раскрытие sidebar**
   - Добавление логики auto-expand при изменении URL
   - Обновление useEffect в AccordionSidebar
   - Сохранение expanded состояния при навигации

4. **Обработка прямых ссылок**
   - Загрузка данных при mount с параметрами из URL
   - Валидация существования thread/session/file
   - Показ загрузчика во время initial load

5. **Валидация и обработка ошибок**
   - Создание RouteGuard компонента
   - Проверка существования ресурсов через API
   - Редирект на главную при невалидных URL

6. **Оптимизация и полировка**
   - Добавление debounce для частых изменений URL
   - Кэширование загруженных данных
   - Плавные переходы между маршрутами

## Критичные граничные случаи

### Обработка файлов с слэшами в пути
- Использование wildcard маршрута (/*) для file path
- Правильное кодирование/декодирование пути в URL
- Сохранение структуры папок в URL

### Гонка состояний при быстрой навигации
- Отмена предыдущих API запросов при новой навигации
- Использование AbortController для отмены fetch
- Проверка актуальности загруженных данных

### Несуществующие ресурсы в URL
- Валидация thread/session/file через API перед отображением
- Graceful fallback на ближайший валидный уровень
- Сохранение частично валидного пути (например, если session не существует, остаться на thread)

### Синхронизация localStorage с URL
- Приоритет URL параметров над localStorage при конфликте
- Обновление localStorage expanded state при навигации через URL
- Очистка устаревших данных из localStorage