// Mock artifact data — заглушки для T6c вьюеров slides/image/audio.
// Группа B: бэкенда нет, данные — локальные константы ({L0.5}).

export interface MockSlide {
  id: number;
  title: string;
  body: string;
}

export interface MockKeyMoment {
  timeLabel: string;
  timeSeconds: number;
  description: string;
}

// --- Slides ---
export const MOCK_SLIDES_TITLE = "Анализ целевой аудитории LearnFlowAI";
export const MOCK_SLIDES_CREATED_AT = "15 июня 2025";

export const MOCK_SLIDES: MockSlide[] = [
  {
    id: 1,
    title: "LearnFlowAI",
    body: "Образовательная платформа на базе AI\nДля структурированного обучения",
  },
  {
    id: 2,
    title: "Целевая аудитория",
    body: "ICP: студенты старших курсов и исследователи\nJTBD: структурировать знания в проектах",
  },
  {
    id: 3,
    title: "Ключевые проблемы",
    body: "Информация разбросана по источникам\nСложно видеть связи между концепциями",
  },
  {
    id: 4,
    title: "Наш подход",
    body: "AI-агент, обучающийся вместе с пользователем\nСфера знаний как живой документ",
  },
  {
    id: 5,
    title: "Метрики успеха",
    body: "Глубина сессий обучения +40%\nВремя до инсайта −35%",
  },
];

// --- Image ---
export const MOCK_IMAGE_TITLE = "Схема архитектуры системы";
export const MOCK_IMAGE_CREATED_AT = "14 июня 2025";
export const MOCK_IMAGE_CAPTION =
  "Сгенерировано агентом · на основе технической документации";

// --- Audio ---
export const MOCK_AUDIO_TITLE = "Запись интервью с пользователем #3";
export const MOCK_AUDIO_CREATED_AT = "13 июня 2025";
export const MOCK_AUDIO_DURATION_SECONDS = 742; // 12:22

export const MOCK_AUDIO_SUMMARY =
  "Пользователь описывает проблему с организацией учебных материалов. " +
  "Текущий процесс: заметки в Notion, закладки в браузере, папки на диске. " +
  "Ключевая боль — потеря контекста при переключении между источниками. " +
  "Ожидаемое решение: инструмент, который «помнит» за него и связывает разрозненные идеи.";

export const MOCK_AUDIO_TRANSCRIPT =
  "00:00  Интервьюер: Расскажите о своём процессе обучения…\n" +
  "00:42  Пользователь: Обычно я начинаю с поиска источников…\n" +
  "03:15  Пользователь: Главная проблема — не могу найти то, что уже читал…\n" +
  "07:28  Пользователь: Мне нужен инструмент, который понимает контекст…\n" +
  "10:55  Пользователь: Если реально экономит время — готов платить…";

export const MOCK_AUDIO_NOTES =
  "Пользователь — студент аспирантуры, 26 лет.\n" +
  "Инструменты: Notion, Google Scholar, Zotero.\n" +
  "Готов платить: «если реально экономит время, то да».\n" +
  "Не любит: избыточные уведомления, сложный onboarding.";

export const MOCK_KEY_MOMENTS: MockKeyMoment[] = [
  {
    timeLabel: "0:42",
    timeSeconds: 42,
    description: "Проблема с поиском информации",
  },
  {
    timeLabel: "3:15",
    timeSeconds: 195,
    description: "Текущий процесс обучения",
  },
  {
    timeLabel: "7:28",
    timeSeconds: 448,
    description: "Ожидания от инструмента",
  },
  {
    timeLabel: "10:55",
    timeSeconds: 655,
    description: "Готовность платить",
  },
];
