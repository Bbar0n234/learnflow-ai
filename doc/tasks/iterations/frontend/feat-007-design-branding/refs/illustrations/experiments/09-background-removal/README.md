# Benchmark удаления фона

Каталог содержит практическое сравнение автоматического удаления кремового фона
из шести утверждённых иллюстраций. Исходные `final/light` и `final/dark` не
изменялись.

## Навигация

- `contact-sheet-methods-light.jpg` — сравнение методов на light-исходниках;
- `contact-sheet-methods-dark.jpg` — сравнение методов на dark-исходниках;
- `contact-sheet-edge-crops.jpg` — увеличенные края и светлые детали;
- `manifest.json` — параметры, метрики и пути всех 78 запусков;
- `metrics-summary.csv` — агрегированная численная сводка;
- `tools/benchmark.py` — воспроизводимый benchmark;
- `tools/summarize.py` — contact sheets и сокращение артефактов.
- `tools/build_candidates.py` — полный прогон `soft-balanced` и `soft-wide`
  по 12 финальным изображениям.

Полные выводы и команды: [transparent-png-research.md](../../../../transparent-png-research.md).
Финальные кандидаты:
[`candidates/transparent/`](../../candidates/transparent/).

## Retention

Полноразмерные `outputs/` всех методов в репозитории не хранятся: численная
история всех 78 запусков зафиксирована в `manifest.json` и `metrics-summary.csv`,
а визуальная — в трёх contact sheets выше. Воспроизвести любой вывод можно
скриптами из `tools/`. Победившие финальные cutout (`soft-balanced`, `soft-wide`
по всем 12 light/dark-картинкам) лежат в
[`candidates/transparent/`](../../candidates/transparent/).

Модельные веса и временное Python-окружение в репозиторий не входят.
