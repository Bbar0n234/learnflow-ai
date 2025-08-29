# Implementation Plan: React Router Deep Linking Integration

## Смысл и цель задачи

Добавление поддержки deep linking через React Router в web-ui приложение LearnFlow AI для обеспечения прямой навигации к конкретным threads, sessions и файлам через URL. Это позволит пользователям делиться ссылками на конкретные материалы и использовать браузерную навигацию (кнопки назад/вперед) для перемещения по приложению.

## Архитектура решения

### Компоненты и модули
- **RouterWrapper** (`src/RouterWrapper.tsx`) - обертка с BrowserRouter и маршрутами
- **AppWithRouter** (`src/AppWithRouter.tsx`) - модифицированный App компонент с поддержкой роутинга
- **RouteGuard** (`src/components/RouteGuard.tsx`) - компонент для валидации маршрутов
- **useNavigation** (`src/hooks/useNavigation.ts`) - хук для навигации и синхронизации состояния
- **useUrlDrivenExpansion** (`src/hooks/useUrlDrivenExpansion.ts`) - хук для определения состояния раскрытия accordion из URL (без localStorage)

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
   - Sidebar раскрывается на основе текущего URL

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

### useUrlDrivenExpansion hook
- **getExpandedFromUrl()** - получение состояния раскрытия из текущего URL
- **expandedThreads** - Set с ID раскрытых threads
- **expandedSessions** - Set с ID раскрытых sessions
- **expandedFolders** - Set с ID раскрытых папок

### RouteGuard component props
- **threadId** - ID thread для проверки
- **sessionId** - ID session для проверки (опционально)
- **filePath** - путь к файлу для проверки (опционально)
- **fallbackPath** - путь для редиректа при ошибке
- **children** - контент для отображения при валидном маршруте

## Взаимодействие компонентов

```
URL изменение -> React Router -> useParams -> AppWithRouter -> State Update -> AccordionSidebar
                                                     |                            |
                                                     v                            v
                                                API calls -> Content     useUrlDrivenExpansion
                                                             Loading      (раскрытие из URL)

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

3. **URL-driven раскрытие sidebar**
   - Создание useUrlDrivenExpansion хука
   - Удаление всей логики localStorage из AccordionSidebar
   - Состояние раскрытия вычисляется только из URL параметров

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

### URL как единственный источник истины
- Полный отказ от localStorage для состояния accordion
- Состояние раскрытия вычисляется исключительно из URL
- При перезагрузке страницы раскрывается только активный путь
- Каждая вкладка браузера имеет независимое состояние

## Детальные шаги реализации

### 1. Создание RouterWrapper (src/RouterWrapper.tsx)
```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppWithRouter from './AppWithRouter';

export const RouterWrapper = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppWithRouter />} />
        <Route path="/thread/:threadId" element={<AppWithRouter />} />
        <Route path="/thread/:threadId/session/:sessionId" element={<AppWithRouter />} />
        <Route path="/thread/:threadId/session/:sessionId/file/*" element={<AppWithRouter />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};
```

### 2. Создание хука useUrlDrivenExpansion (src/hooks/useUrlDrivenExpansion.ts)
```typescript
import { useParams } from 'react-router-dom';
import { useMemo } from 'react';

export const useUrlDrivenExpansion = () => {
  const params = useParams();
  const { threadId, sessionId } = params;
  const filePath = params['*']; // для wildcard route
  
  const expanded = useMemo(() => {
    const expandedThreads = new Set<string>();
    const expandedSessions = new Set<string>();
    const expandedFolders = new Set<string>();
    
    // Если есть threadId в URL - раскрываем этот thread
    if (threadId) {
      expandedThreads.add(threadId);
    }
    
    // Если есть sessionId в URL - раскрываем эту session
    if (sessionId && threadId) {
      expandedSessions.add(`${threadId}-${sessionId}`);
    }
    
    // Если есть файл с путём - раскрываем папки
    if (filePath && filePath.includes('/')) {
      const parts = filePath.split('/');
      parts.pop(); // убираем имя файла
      
      let currentPath = '';
      parts.forEach(folder => {
        currentPath = currentPath ? `${currentPath}/${folder}` : folder;
        expandedFolders.add(`${threadId}-${sessionId}-${currentPath}`);
      });
    }
    
    return {
      threads: expandedThreads,
      sessions: expandedSessions,
      folders: expandedFolders
    };
  }, [threadId, sessionId, filePath]);
  
  return expanded;
};
```

### 3. Модификация AccordionSidebar для URL-driven состояния
```tsx
// Удаляем всю логику localStorage и заменяем на useUrlDrivenExpansion
import { useUrlDrivenExpansion } from '../hooks/useUrlDrivenExpansion';

export const AccordionSidebar: React.FC<AccordionSidebarProps> = ({
  threads,
  sessionFiles,
  selectedThread,
  selectedSession,
  selectedFile,
  onSelect,
}) => {
  // Получаем состояние раскрытия из URL
  const expanded = useUrlDrivenExpansion();
  
  // Удаляем все useState, useEffect с localStorage
  // Удаляем функции toggleThread, toggleSession, toggleFolder
  
  // В рендере используем expanded напрямую:
  const isThreadExpanded = expanded.threads.has(thread.thread_id);
  const isSessionExpanded = expanded.sessions.has(sessionKey);
  const isFolderExpanded = expanded.folders.has(folderId);
  
  // Клики теперь только вызывают onSelect для навигации
  onClick={() => onSelect(thread.thread_id)}
  onClick={() => onSelect(thread.thread_id, session.session_id)}
  onClick={() => onSelect(thread.thread_id, session.session_id, file.path)}
};
```

### 4. Модификация App.tsx для использования навигации
```tsx
import { useNavigate, useParams } from 'react-router-dom';

function AppWithRouter() {
  const navigate = useNavigate();
  const params = useParams();
  const { threadId, sessionId } = params;
  const filePath = params['*'];
  
  // Состояние инициализируется из URL параметров
  const [appState, setAppState] = useState<AppState>({
    selectedThread: threadId || null,
    selectedSession: sessionId || null,
    selectedFile: filePath || null,
    // ...
  });
  
  // Модифицируем handleSelect для навигации
  const handleSelect = (threadId: string, sessionId?: string, filePath?: string) => {
    // Формируем URL на основе выбора
    let url = '/';
    if (threadId) {
      url = `/thread/${threadId}`;
      if (sessionId) {
        url += `/session/${sessionId}`;
        if (filePath) {
          url += `/file/${filePath}`;
        }
      }
    }
    
    // Навигация изменит URL и вызовет перерендер
    navigate(url);
  };
  
  // Синхронизация с URL при изменении параметров
  useEffect(() => {
    setAppState(prev => ({
      ...prev,
      selectedThread: threadId || null,
      selectedSession: sessionId || null,
      selectedFile: filePath || null,
    }));
    
    // Загружаем данные если нужно
    if (threadId && sessionId && filePath) {
      loadFileContent(threadId, sessionId, filePath);
    }
  }, [threadId, sessionId, filePath]);
}
```

### 5. Обновление main.tsx
```tsx
import { RouterWrapper } from './RouterWrapper';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterWrapper />
  </StrictMode>,
);
```

## Риски и их митигация

1. **Потеря состояния раскрытия при навигации**
   - Риск: Пользователь может быть разочарован, что раскрытые элементы сворачиваются
   - Митигация: Четкая визуальная индикация активного пути, быстрая анимация раскрытия

2. **Производительность при частой навигации**
   - Риск: Частые перерендеры при изменении URL
   - Митигация: Использование useMemo в useUrlDrivenExpansion, React.memo для компонентов

3. **Невалидные URL при прямом доступе**
   - Риск: 404 ошибки или белый экран
   - Митигация: RouteGuard с валидацией и graceful fallback