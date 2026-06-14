# Manifest генерации брендовых иллюстраций

Документ содержит канонические входы для повторной генерации финального UI-пака.
Общий визуальный язык и базовый блок промпта находятся в
[`illustration-style-guide.md`](illustration-style-guide.md). Для каждой новой
light-генерации базовый блок дополняется одним scene-блоком ниже.

## Референсы

Для всех финальных сцен:

- style и density reference:
  [`welcome-hero.png`](refs/illustrations/final/light/welcome-hero.png);
- характер сказочной продуктовой врезки:
  [`ref-09-panel.jpg`](refs/illustrations/experiments/06-source-preparation/ref-09-panel.jpg),
  только как mood reference, без копирования композиции;
- identity reference кота:
  [`welcome-explore2-v1.png`](refs/illustrations/experiments/02-character-calibration/welcome-explore2-v1.png).

При генерации сцены без кота последний референс не прикладывается. Утверждённые
человеческие персонажи пока существуют только внутри финальных сцен; отдельные
character sheets для них не создавались.

## Scene-блоки

### `welcome-hero.png`

```text
Asset type: welcome screen hero illustration, landscape 16:9.
Scene: The adult scholar cat stands at the right, calmly welcoming the viewer
with one open conversational paw. A violet knowledge orb floats nearby. Arrange
an open book, a short stack of books, a floating teapot pouring into a cup, two
simple alchemy flasks, a quill, small sparks, and a few lavender magical curls
as one compact fairytale constellation around the cat.
Composition: Keep at least 40–45% clean negative space on the left. The pose
must communicate waiting, greeting, and invitation, not travel or action.
```

### `sidebar-vignette.png`

```text
Asset type: compact sidebar vignette, very wide 3:1 to 4:1.
Scene: The same adult scholar cat rests lengthwise on one thick closed book,
awake and calm rather than pet-like. Around the book place a tiny floating
teapot and cup, two simple flasks, a small violet knowledge orb, a loose page,
a quill, a few sparks, and restrained lavender curls.
Composition: One low horizontal cluster with generous empty space above and at
both sides. Keep every supporting object readable at small UI size.
```

### `empty-chats.png`

```text
Asset type: empty-state illustration, approximately 4:3.
Scene: A kind adult storyteller grandfather sits cross-legged on a simple
flying carpet and extends one hand in an inviting "where shall we begin?"
gesture. Around him float an open book, one closed book, a violet knowledge
orb, a teapot pouring into a cup, one small flask, loose pages, a quill, sparks,
and a few lavender magical curls.
Character: Wise, warm, slightly witty, clearly adult; simple cream beard,
rounded glasses, violet cap and robe. Avoid childish or wizard-costume excess.
```

### `empty-sphere.png`

```text
Asset type: empty knowledge-sphere state, approximately 4:3.
Scene: The same adult scholar cat stands beside a nearly empty translucent
lavender knowledge sphere and gently adds one small spark to it. A graceful
Firebird assists by offering a violet quill. Include an open book, two closed
books, a floating cup, two simple flasks, loose pages, small sparks, and
lavender magical curls.
Composition: Keep the sphere as the semantic center. The Firebird must remain a
clean editorial shape, not detailed fantasy concept art.
```

### `empty-artifacts.png`

```text
Asset type: empty artifacts state, approximately 4:3.
Scene: Vasilisa kneels beside an open wooden chest while a blank sheet rises
from it and begins to become a magical artifact. Add an open book, a short
book stack with a teapot, a cup, two simple flasks, loose blank pages, a violet
knowledge orb, a quill, small sparks, and lavender curls.
Character: Adult, calm and capable, with a simple braid and restrained
cream/violet clothing. No princess glamour, embroidery overload, or realism.
```

### `error-state.png`

```text
Asset type: friendly error-state illustration, approximately 4:3.
Scene: Adult Ivan stands beside a simple cream fairytale stove that has stopped
working and releases one crooked lavender curl. Ivan scratches his head with
good-natured confusion. The adult scholar cat sits nearby and looks calmly at
the viewer. Add an open book, one closed book, two loose pages, a fallen cup,
a small flask, a violet orb, a quill, and a few restrained sparks.
Mood: "Something went wrong, but it is manageable." No panic, damage, fire,
slapstick, or childish stupidity.
```

## Инварианты

- Сначала генерируется light-исходник на кремовом фоне.
- Dark-пара создаётся генеративным edit по утверждённому режиму B из
  [`dark-theme-adaptation.md`](dark-theme-adaptation.md). Кремовый фон не
  перекрашивается, потому что позже удаляется отдельным pipeline.
- Небольшое смещение внутренних линий допустимо, если не заметно при обычном
  переключении темы. Композиция, персонажи, силуэты и набор объектов должны
  оставаться визуально теми же.
- Количество предметов можно варьировать внутри указанного набора, но не
  заменять предметную насыщенность текстурами и рендерингом.
- Для новой композиции эталон задаёт рисовку, палитру и плотность, но не
  расположение объектов.
- Текстовый prompt без референса используется только для исследования.
- После генерации проверяются взрослый тон, идентичность персонажей, отсутствие
  текста, чистый фон, читаемость на целевом размере и свободное место для UI.
