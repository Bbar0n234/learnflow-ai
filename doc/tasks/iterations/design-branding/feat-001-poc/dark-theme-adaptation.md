# Адаптация иллюстраций к тёмной теме

Dark-версия создаётся генеративным edit исходной light-картинки по режиму B.
Этот процесс утверждён для MVP. Кремовый фон сохраняется: его удаление —
отдельный pipeline, описанный в
[`transparent-png-research.md`](transparent-png-research.md).

## Инварианты

Модель получает light-изображение как edit target и должна сохранить:

- canvas, соотношение сторон и кроп;
- композицию, позиции и количество объектов;
- силуэты, позы, лица и идентичность персонажей;
- толщину и маршруты контуров;
- стиль рисовки и предметную насыщенность.

Меняются только цвета, необходимые для размещения будущего cutout на
`#181420`: наружные контуры, тени, тонкие линии, эффекты и, в расширенном режиме,
основные foreground-заливки.

Генеративная модель не гарантирует буквальную идентичность пикселей. Требование
«pixel-perfect» здесь означает целевой инвариант композиции, но результат всегда
проверяется на случайное смещение линий и мелких объектов.

## Выбранный режим

Для финального пакета используется режим B: адаптация foreground-палитры.
Небольшое генеративное смещение отдельных пикселей и внутренних линий допустимо,
если оно не бросается в глаза при переключении тем и не меняет композицию,
персонажа или набор объектов.

Все шесть утверждённых dark-версий находятся в
[`refs/illustrations/final/dark/`](refs/illustrations/final/dark/). Сравнение
light/dark-пар:
[`light-dark-contact-sheet.png`](refs/illustrations/final/light-dark-contact-sheet.png).

## Исследованные режимы

### A: только края и эффекты

Основные заливки персонажей и предметов сохраняются. Разрешено менять:

- наружные контуры, исчезающие на тёмном фоне;
- контактные и падающие тени;
- тонкие внутренние линии;
- дымки, искры и cream-contamination на антиалиасинге.

Результат: модель хорошо удерживает исходник, но изменение получается слишком
слабым. Чёрный кот после удаления фона всё ещё рискует сливаться с UI.

### B: адаптация foreground-палитры

Дополнительно разрешено:

- сдвинуть чёрный мех в глубокий charcoal-violet;
- сделать светлые страницы и одежду мягким luminous cream/lavender;
- перенастроить violet, teal и gold для контраста;
- осветлить только те внешние контуры, которые исчезнут на `#181420`.

Результат: адаптация заметнее и ближе к полноценной dark-теме. Модель слегка
перерисовывает отдельные внутренние линии и мелкие детали, но такой сдвиг принят
как допустимый для MVP при обязательном визуальном контроле каждой сцены.

## Материалы

Тест проведён на `welcome-hero`, `empty-sphere` и `empty-artifacts`.

- сравнение source / режим A / режим B:
  [`contact-sheet-source-a-b.png`](refs/illustrations/experiments/08-dark-generative/contact-sheet-source-a-b.png)
  (на одном листе видно оба исследованных режима);
- отвергнутый deterministic baseline:
  [`light-dark-contact-sheet.png`](refs/illustrations/experiments/07-dark-deterministic-rejected/light-dark-contact-sheet.png).

Режим B утверждён. Полноразмерные промежуточные копии прогонов не хранятся —
история зафиксирована в сводных contact sheets выше; финальные dark-версии лежат
в [`refs/illustrations/final/dark/`](refs/illustrations/final/dark/).

## Prompt-шаблон

```text
Use the light illustration as the edit target. Adapt only the existing
foreground palette for clean placement on a #181420 dark product UI. Keep the
cream background unchanged because background extraction is a separate task.

Preserve canvas, crop, composition, positions, object count, silhouettes,
poses, faces, character identity, contour paths, line thickness, style and
detail density. Do not add, remove, move or reshape anything.

Adapt outer contours, contact shadows, thin lines, magical effects and
antialiased edge contamination. Gently adapt dark and light foreground fills
while preserving violet, muted teal and gold brand identity.

No text, logo, new texture, lighting, gradient, 3D treatment or restyling.
```
