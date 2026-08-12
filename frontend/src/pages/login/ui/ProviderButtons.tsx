import { Button } from "@/shared/ui/button";
import type { ProviderEntry } from "./provider-registry";

export interface ProviderButtonsProps {
  entries: ProviderEntry[];
  onSelect: (providerId: string) => void;
}

/**
 * Локальный презентационный блок кнопок провайдеров каркаса `/login`.
 * Вызывающая сторона (`LoginPage`) отвечает за то, чтобы `entries` не был
 * пустым — пустой список означает отсутствие блока целиком (в т.ч.
 * разделителя «или»), это решается на уровне `LoginScreenView`.
 */
export function ProviderButtons({ entries, onSelect }: ProviderButtonsProps) {
  return (
    <div className="flex flex-col gap-2">
      {entries.map((entry) => (
        <Button
          key={entry.id}
          type="button"
          variant="outline"
          size="lg"
          className="w-full"
          onClick={() => onSelect(entry.id)}
        >
          {entry.label}
        </Button>
      ))}
    </div>
  );
}
