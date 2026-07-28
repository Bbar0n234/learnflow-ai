/**
 * Плейсхолдер на время генерации изображения — живёт от начала вызова
 * `generate_image` до его результата. Вёрстка — та же карточка, что `ArtifactCard`
 * (тот же бордер/паддинг/borderLeft), зона превью — шиммер, заголовок «Генерирую
 * изображение…», прогресс-бар — indeterminate (реального прогресса генерация не
 * отдаёт). По мокапу `image-artifacts.html` § `#genCardRow`.
 */
export function GeneratingArtifactCard() {
  return (
    <div
      role="status"
      aria-label="Идёт генерация изображения"
      className="mt-2 flex items-center gap-3 rounded-md bg-card p-3"
      style={{ borderLeft: "3px solid var(--ring)" }}
    >
      <div
        aria-hidden="true"
        className="h-10 w-16 shrink-0 animate-pulse rounded-sm border border-border bg-muted"
      />
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-muted-foreground">
          Генерирую изображение…
        </p>
        <span className="mt-1.5 block h-[3px] w-40 max-w-full overflow-hidden rounded-full bg-muted">
          <span className="gen-progress-run block h-full w-2/5 rounded-full bg-primary" />
        </span>
      </div>
    </div>
  );
}
