# Архив брендовых иллюстраций

Каталог разделяет утверждённый UI-пак и историю экспериментов. Актуальные правила
рисовки, базовый промпт и процесс воспроизведения описаны в
[`illustration-style-guide.md`](../../illustration-style-guide.md).

## Финальный пакет

`final/light/` и `final/dark/` содержат шесть утверждённых сцен:

- `welcome-hero.png`;
- `sidebar-vignette.png`;
- `empty-chats.png`;
- `empty-sphere.png`;
- `empty-artifacts.png`;
- `error-state.png`.

Dark-пак создан генеративным edit по режиму B. Кремовый фон обеих версий пока
остаётся в изображениях и будет удалён отдельным pipeline. Допустимы небольшие
незаметные расхождения внутренних линий; композиция, персонажи и объекты
сохраняются. Итоговое сравнение —
[`final/light-dark-contact-sheet.png`](final/light-dark-contact-sheet.png).
Процесс и prompt-шаблон описаны в
[`dark-theme-adaptation.md`](../../dark-theme-adaptation.md).

Косчей, Баба-яга и Змей Горыныч не входят в обязательные шесть UI-состояний.
Они сохранены как расширение библиотеки персонажей и кандидаты для будущих
сценариев.

## История экспериментов

Хронология итерации с итогом каждого шага. Полноразмерные промежуточные
генерации в репозитории не хранятся — история зафиксирована в сводных contact
sheets (колонка «Артефакт»); этапы `00`/`01` сохранены только как запись в этой
таблице. Финальные ассеты живут в `final/`, прозрачные cutout — в
`candidates/transparent/`.

| Этап | Что проверялось | Итог | Артефакт в репо |
|---|---|---|---|
| `00-initial-calibration` | Первые трактовки welcome-сцены | Отказ от чрезмерного минимализма и Adventure Time как языка рисовки | — (только запись) |
| `01-composition-matrix` | 4 композиции × 4 стилистические трактовки | Потребовались более встречающие позы и большая вариативность | — (только запись) |
| `02-character-calibration/` | Восемь вариантов кота | `welcome-explore2-v1.png` выбран как эталон идентичности | `welcome-explore2-v1.png` |
| `03-style-transfer/` | С референсом, без референса, люди и группы | Визуальный референс нужен для финальной серии; текстовый промпт годится для поиска идей | 2 contact sheets |
| `04-detail-density/` | Книги, чай, алхимия и смешанная сцена | Вариант `d4-mixed` выбран как нужная предметная насыщенность | `welcome-detail-contact-sheet.png` |
| `05-expanded-series/` | Остальные UI-сцены и дополнительные герои | Пять сцен вошли в финальный пакет; три героя оставлены как расширение | `series-expanded-contact-sheet.png` |
| `06-source-preparation/` | Кроп Zapier ref-09 и технические тайлы | Вспомогательные исходники, не финальные ассеты | `ref-09-panel.jpg` |
| `07-dark-deterministic-rejected/` | Скриптовая перекраска foreground и фона | Отброшено: шероховатые края, контуры и цветные ореолы | `light-dark-contact-sheet.png` |
| `08-dark-generative/` | Генеративные режимы A и B | Режим B выбран и применён ко всем шести сценам | `contact-sheet-source-a-b.png` |
| `09-background-removal/` | 78 запусков ImageMagick, color-to-alpha, PyMatting и CPU ML | Benchmark завершён; два soft-профиля вынесены в полный candidate-пак | 3 contact sheets, `manifest.json`, `metrics-summary.csv`, `tools/` |

Прозрачный фон в итоге вырезан managed-моделью **BiRefNet General-HR** (бесплатно
через Hugging Face Space) — примеры в
[`managed-service-examples/`](managed-service-examples/), исследование сервисов в
[`background-removal-services-research.md`](../../background-removal-services-research.md).
Локальный детерминированный fallback — два актуальных кандидата в
[`candidates/transparent/`](candidates/transparent/): `soft-balanced` и
`soft-wide`. Оба обработаны на всех 12 light/dark-файлах и ожидают аппрува.
SVG-векторизация до выбора не запускается.

Главный практический вывод: детализация серии создаётся количеством простых
предметов и сказочными взаимодействиями между ними, а не текстурами, штриховкой
или сложным светом.
