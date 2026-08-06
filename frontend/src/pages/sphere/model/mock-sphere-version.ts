// Mock sphere version data — stub для T6b семвер-UI, без бэкенд-контракта (группа B).
// Реальный источник (версионирование при сохранении сферы + хроника) — в бэклоге брифа feat-004.

export type SphereVersionBump = "мажор" | "минор" | "патч";

export interface SphereVersionEntry {
  version: string;
  summary: string;
  author: "agent" | "user";
  timestamp: string;
  bump: SphereVersionBump;
  /** true = акцентная точка в хронике (новое); false/undefined = сиреневая (старое) */
  isNew?: boolean;
}

export interface SphereStats {
  records: number;
  connections: number;
  versions: number;
}

export const MOCK_SPHERE_CURRENT_VERSION = "v2.4.1";
export const MOCK_SPHERE_STATUS = "растёт";

export const MOCK_SPHERE_STATS: SphereStats = {
  records: 42,
  connections: 18,
  versions: 7,
};

/** История версий, новейшая первой */
export const MOCK_SPHERE_HISTORY: SphereVersionEntry[] = [
  {
    version: "v2.4.1",
    summary: "Уточнён JTBD для сегмента «студенты»",
    author: "agent",
    timestamp: "2 часа назад",
    bump: "патч",
    isNew: true,
  },
  {
    version: "v2.4.0",
    summary: "Добавлен раздел «Ценностное предложение»",
    author: "agent",
    timestamp: "вчера",
    bump: "минор",
    isNew: false,
  },
  {
    version: "v2.3.0",
    summary: "Реструктуризация разделов продукта",
    author: "user",
    timestamp: "3 дня назад",
    bump: "минор",
    isNew: false,
  },
  {
    version: "v2.0.0",
    summary: "Обновлена вся структура сферы",
    author: "user",
    timestamp: "неделю назад",
    bump: "мажор",
    isNew: false,
  },
];

/** Текущее предложение агента по уровню следующего сохранения */
export const MOCK_AGENT_SUGGESTION: SphereVersionBump = "патч";
