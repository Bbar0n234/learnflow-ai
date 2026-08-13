export interface ProviderEntry {
  id: string;
  label: string;
}

// Локальный реестр подписей провайдеров в фиксированном порядке отображения
// (design-brief.md § Целевой УX, тексты — из мокапа feat-013). Порядок
// записей реестра и есть порядок рендера — независимо от порядка серверного
// массива `providers` или от того, какой трек его формирует.
const PROVIDER_REGISTRY: readonly ProviderEntry[] = [
  { id: "yandex", label: "Войти с Яндекс ID" },
  { id: "google", label: "Войти через Google" },
  { id: "github", label: "Войти через GitHub" },
];

/**
 * Пересечение локального реестра (порядок, подписи) с серверным списком
 * `providers` (состав). Позитивный предикат по построению: неизвестный
 * серверный id просто не встречается в реестре и не рендерится; провайдер
 * из реестра без записи в `providers` тоже не рендерится.
 */
export function getActiveProviders(providers: string[]): ProviderEntry[] {
  return PROVIDER_REGISTRY.filter((entry) => providers.includes(entry.id));
}
