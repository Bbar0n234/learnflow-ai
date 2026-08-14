import { StateScreen } from "@/shared/ui/StateScreen";

/**
 * Empty-state вкладки «Артефакты» — ничего не выбрано в списке слева
 * (feat-013, блок 6.2 дизайн-брифа). Без заголовка — только сцена и подпись.
 *
 * Рендерится индекс-роутом `artifacts` внутри `ArtifactsPage`, чей вьюер —
 * flex-контейнер (`flex min-w-0 flex-1 overflow-hidden`), поэтому базовый
 * `flex-1` из `StateScreen` центрирует блок без дополнительных классов.
 *
 * Сцена 440px — решение архитектора сверх мокапа (там 300px): панель вьюера
 * занимает большую часть экрана, и сцена паритетна empty-state сферы.
 */
export function NoArtifactSelected() {
  return (
    <StateScreen
      scene="artifacts-select"
      alt="Иллюстрация: выберите артефакт"
      illustrationClassName="max-w-[440px]"
      description="Выберите артефакт из списка слева, чтобы посмотреть его."
    />
  );
}
