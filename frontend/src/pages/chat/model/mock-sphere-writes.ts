// Mock sphere write events — stub data для peek S3, без бэкенд-контракта (группа B).
// Реальный источник (SSE-событие «агент пишет в сферу» + версионирование) — в бэклоге брифа feat-004.

export interface SphereWriteEntry {
  id: string;
  section: string;
  versionFrom: string;
  versionTo: string;
  bumpType: "патч" | "минор" | "мажор";
  diff: string[];
}

export const MOCK_SPHERE_WRITES: SphereWriteEntry[] = [
  {
    id: "sw-1",
    section: "Концепция продукта",
    versionFrom: "v2.4.0",
    versionTo: "v2.4.1",
    bumpType: "патч",
    diff: [
      "+ Добавлен абзац о ценностном предложении для сегмента «студенты».",
      "+ Уточнён JTBD: «когда я теряю нить обучения, я хочу быстро восстановить контекст».",
    ],
  },
];
