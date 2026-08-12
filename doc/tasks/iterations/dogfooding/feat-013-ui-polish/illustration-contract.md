# Контракт генерации: три новые сцены серии «Электрик» (feat-013)

Контракт для image-генерации (Codex): три новые сцены расширяют утверждённую брендовую серию иллюстраций. Состав сцен и распределение персонажей утверждены архитектором. Итог работы по контракту — light-исходник + dark-пара для каждой сцены, на кремовом фоне (фон удаляется позже отдельным pipeline, здесь его не трогать).

## Источники истины (читать перед генерацией, приоритет при расхождении — сверху вниз)

1. [`illustration-style-guide.md`](../../design-branding/feat-001-poc/illustration-style-guide.md) — паспорт стиля серии: визуальный язык, эталон кота, палитра, базовый блок промпта, рабочий процесс.
2. [`illustration-generation-manifest.md`](../../design-branding/feat-001-poc/illustration-generation-manifest.md) — канонические scene-блоки существующей серии и инварианты (взрослый тон, без текста, чистый фон, свободный воздух).
3. [`dark-theme-adaptation.md`](../../design-branding/feat-001-poc/dark-theme-adaptation.md) — режим B для dark-пары: генеративный edit light-исходника, кремовый фон не перекрашивать.

## Binding-референсы (прикладывать к каждой генерации)

| Что фиксирует | Файл |
|---|---|
| Рисовка, палитра, плотность сцены | `../../design-branding/feat-001-poc/refs/illustrations/final/light/welcome-hero.png` |
| Идентичность кота (сцена 3) | `../../design-branding/feat-001-poc/refs/illustrations/experiments/02-character-calibration/welcome-explore2-v1.png` |
| Идентичность Ивана (сцена 1) | `../../design-branding/feat-001-poc/refs/illustrations/final/light/error-state.png` |
| Идентичность Василисы (сцена 2) | `../../design-branding/feat-001-poc/refs/illustrations/final/light/empty-artifacts.png` |

Персонажи уже откалиброваны серией — калибровочный стоп-гейт не требуется; сохранять идентичность по референсам, случайный редизайн персонажа = брак.

## Сцены

Каждый промпт = базовый блок из style-guide + scene-блок ниже. Генерить в максимальном доступном разрешении, соотношение ~4:3; точные пиксели не важны — важны соотношение и свободный воздух по краям. Без текста, букв и цифр на изображении (инвариант серии — смысл «404» передаётся предметно, не цифрами).

### 1. `not-found.png` — экран 404 «страница не найдена»

```text
Asset type: 404 not-found state, approximately 4:3.
Scene: Adult Ivan stands at a fairytale crossroads beside a large rounded
waystone (the classic Russian tale signpost stone). The stone's sign areas are
blank, and the two paths behind it dissolve into soft lavender curls instead of
leading anywhere. Ivan holds up a simple lantern and looks at the stone with
good-natured puzzlement. At his feet: a rolled map scroll, one closed book, a
small violet knowledge orb, and a few restrained sparks.
Mood: "This road does not exist, but the way back is right here." Calm, mildly
ironic, no panic, no darkness, no danger.
Character: Ivan exactly as in the error-state reference — cream kosovorotka
shirt with thin violet belt, bowl-cut light hair, dot eyes, noodle limbs. The
stove stays home: no stove in this scene.
```

### 2. `artifacts-select.png` — «выберите артефакт из списка»

```text
Asset type: artifact-selection state (artifacts exist, none chosen yet),
approximately 4:3.
Scene: Vasilisa stands before three or four finished scroll-artifacts floating
in a gentle semicircle at her eye level. She reaches toward one of them; that
scroll is highlighted by two or three small sparks. The scrolls are simple flat
shapes with a subtle violet accent. Add a low book stack, a floating cup, one
flask, and a small violet knowledge orb as supporting objects.
Composition: The choice gesture is the semantic center — Vasilisa's hand and
the highlighted scroll. Unlike the empty-artifacts scene, the artifacts here
are already made: no chest, no birth-of-artifact motif.
Character: Adult, calm and capable, with a simple braid and restrained
cream/violet clothing, exactly as in the empty-artifacts reference.
```

### 3. `auth-hero.png` — экран входа `/login`

```text
Asset type: login-page hero illustration, approximately 4:3.
Scene: The adult scholar cat hospitably opens the door of a small fairytale
library-hut, inviting the viewer inside. Warm golden light and tall book
stacks show through the doorway. A simple key hangs on the cat's thin chain
next to the glasses. The cat's gesture is welcoming — one paw holds the door,
the other gently invites. Add a doormat-like loose page, a floating cup, a
small violet knowledge orb, and a few sparks near the doorway.
Composition: Character and door on the right side, at least 40 percent of the
left side stays as free air (the login form card lives there in the UI).
Mood: threshold and welcome — "come in, your projects are waiting" — calm and
warm, not a journey scene.
```

## Dark-пары

После каждого light-исходника — dark-версия генеративным edit по режиму B (`dark-theme-adaptation.md`): адаптируется только foreground, кремовый фон остаётся. Композиция, персонажи, силуэты и набор объектов — визуально те же.

## Критерии приёмки (самопроверка после каждой генерации, до 3 попыток на сцену)

- Палитра серии не нарушена, никаких посторонних цветов; фон сплошной кремовый.
- Контур чистый средней толщины, матовые заливки, без градиентов/3D/текстур/сложного света.
- Идентичность персонажа совпадает с binding-референсом (Иван / Василиса / кот: очки+цепочка).
- Взрослый тон, никакой детскости и слапстика; без текста, букв и цифр.
- Компактный смысловой кластер, свободный воздух по краям (сцена 3 — слева ≥40%).
- Dark-пара визуально идентична light по композиции.

## Перегенерация: итерация 2 (фидбэк архитектора по итерации 1)

Сцены 1 и 2 приняты, их не трогать. Перегенерируется **только `auth-hero.png`** — дефект первой генерации: **хвост кота зажат открытой дверью** (проходит за дверным полотном и выглядит прищемлённым).

```text
Regenerate auth-hero. Use the previous generation
(generated/light/auth-hero.png) as the binding composition reference: keep the
same scene, character identity, door, hut, doorway light, key on chain, doormat
page, supporting objects, palette, and left-side free air.
Fix exactly one thing: the cat's tail must not be caught behind or pinched by
the open door. The tail lies freely and fully visible — curled calmly beside
the cat's feet or wrapped around them, entirely in front of the door plane.
```

После light-версии — dark-пара тем же режимом B. Результат кладётся поверх прежних файлов (`generated/{light,dark}/auth-hero.png`) — история остаётся в git.

## Куда класть результат

`doc/tasks/iterations/dogfooding/feat-013-ui-polish/generated/{light,dark}/<имя-сцены>.png` — в ветку `dogf/feat-013-ui-polish`. Варианты (если несколько кандидатов на сцену) — с суффиксами `-v1/-v2`. Дальнейшие шаги вне этого контракта: отбор архитектором → BiRefNet-вырез → ручная доводка → вставка в мокап итерации → перенос в `frontend/src/shared/assets/illustrations/` при реализации.
