# Implementation Plan: React SPA Iteration 2 - Basic Web Interface

## Архитектура решения

### Общая архитектура
React SPA будет создан как отдельный модуль в существующем uv workspace, интегрирующийся с уже работающим Artifacts Service. Приложение построено на:
- **Vite + React + TypeScript** для быстрой разработки и типизации
- **Tailwind CSS** для стилизации с поддержкой темной/светлой темы
- **React Markdown** с LaTeX поддержкой для рендеринга материалов
- **Axios** для HTTP клиента к Artifacts Service

### Файловая структура
```
web-ui/                          # Новая директория в корне проекта
├── package.json                 # npm зависимости и скрипты
├── vite.config.ts              # Vite конфигурация
├── tsconfig.json               # TypeScript настройки
├── tailwind.config.js          # Tailwind конфигурация
├── index.html                  # HTML точка входа
├── src/
│   ├── main.tsx                # React точка входа
│   ├── App.tsx                 # Основной компонент приложения
│   ├── index.css               # Глобальные стили
│   ├── components/             # React компоненты
│   │   ├── Layout.tsx          # Основной layout
│   │   ├── FileExplorer.tsx    # Древовидное отображение файлов
│   │   ├── MarkdownViewer.tsx  # Рендеринг Markdown с LaTeX
│   │   ├── ThreadsList.tsx     # Список threads
│   │   ├── SessionsList.tsx    # Список sessions в thread
│   │   └── ThemeToggle.tsx     # Переключатель темы
│   ├── services/               # API слой
│   │   ├── ApiClient.ts        # HTTP клиент к Artifacts Service
│   │   └── types.ts            # TypeScript типы для API
│   ├── hooks/                  # React hooks
│   │   ├── useApi.ts           # Hook для API запросов
│   │   └── useTheme.ts         # Hook для управления темой
│   └── utils/                  # Утилиты
│       └── constants.ts        # Константы приложения
└── public/                     # Статические файлы
    └── vite.svg                # Иконка приложения
```

## API и интерфейсы

### ApiClient класс
```typescript
class ApiClient {
  private baseURL: string;
  private axiosInstance: AxiosInstance;

  // Получение списка threads
  getThreads(): Promise<ThreadsListResponse>
  
  // Получение информации о thread
  getThread(threadId: string): Promise<ThreadDetailResponse>
  
  // Получение файлов session
  getSessionFiles(threadId: string, sessionId: string): Promise<SessionFilesResponse>
  
  // Получение содержимого файла
  getFileContent(threadId: string, sessionId: string, filePath: string): Promise<string>
  
  // Создание/обновление файла
  createOrUpdateFile(threadId: string, sessionId: string, filePath: string, content: string): Promise<FileOperationResponse>
  
  // Удаление файла
  deleteFile(threadId: string, sessionId: string, filePath: string): Promise<FileOperationResponse>
}
```

### TypeScript типы
```typescript
interface Thread {
  thread_id: string;
  sessions_count: number;
  created: string;
  last_activity: string;
}

interface Session {
  session_id: string;
  files_count: number;
  created: string;
  last_modified: string;
}

interface FileInfo {
  name: string;
  path: string;
  size: number;
  modified: string;
  content_type: string;
}

interface AppState {
  selectedThread: string | null;
  selectedSession: string | null;
  selectedFile: string | null;
  currentFileContent: string | null;
  isLoading: boolean;
  error: string | null;
}
```

### Основные hooks
```typescript
// useApi.ts - для управления API запросами
const useApi = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const executeRequest = async <T>(request: Promise<T>): Promise<T | null>;
  
  return { isLoading, error, executeRequest };
}

// useTheme.ts - для управления темой
const useTheme = () => {
  const [isDark, setIsDark] = useState<boolean>();
  
  const toggleTheme = () => void;
  
  return { isDark, toggleTheme };
}
```

## Взаимодействие компонентов

### Поток данных
1. **App.tsx** управляет глобальным состоянием (selectedThread, selectedSession, selectedFile)
2. **Layout.tsx** содержит общую структуру и передает состояние дочерним компонентам
3. **ThreadsList.tsx** отображает список threads и обновляет selectedThread
4. **FileExplorer.tsx** получает files через API когда selectedSession изменяется
5. **MarkdownViewer.tsx** загружает и рендерит содержимое когда selectedFile изменяется

### Состояние и пропсы
- Глобальное состояние в App.tsx с useState
- Передача callbacks для обновления состояния через props
- Локальное состояние в компонентах для UI specifics (loading states, etc.)

### Обработка ошибок
- Централизованная обработка HTTP ошибок в ApiClient
- Отображение error messages в UI компонентах
- Fallback UI для случаев когда данные недоступны

## Edge Cases и особенности

### Навигация и URL состояние
- Использовать browser history для navigation state
- URL pattern: `/{threadId}/{sessionId}/{filePath}`
- Deep linking support для прямых ссылок на файлы

### Производительность
- Lazy loading для больших Markdown файлов
- Virtualization для больших списков threads/sessions (если потребуется)
- Мemoization для дорогих рендеров (React.memo, useMemo)

### Безопасность
- Валидация всех user inputs
- Sanitization Markdown content (react-markdown уже обеспечивает)
- Proper error handling для предотвращения information disclosure

### Responsive дизайн
- Mobile-first approach с Tailwind breakpoints
- Collapsible sidebar для мобильных устройств
- Touch-friendly navigation elements

### LaTeX рендеринг
- Использование rehype-katex для математических формул
- Поддержка inline и block математики
- Fallback для случаев parsing errors

### Темная/светлая тема
- CSS custom properties для цветовых переменных
- LocalStorage для сохранения предпочтений пользователя
- Smooth transitions между темами

### Обработка различных типов файлов
- Markdown файлы → MarkdownViewer с LaTeX support
- JSON файлы → formatted JSON display
- Plain text → простой text viewer
- Binary files → download links или "cannot preview" message

### Оптимизация загрузки
- Debouncing для API calls при быстром переключении
- Caching recently loaded content
- Progressive enhancement для better UX

### Интеграция с uv workspace
- Добавление web-ui в pyproject.toml workspace members
- npm scripts для development и build
- Docker integration для production deployment