# Паспорт стиля брендовых иллюстраций

Документ фиксирует утверждённый стиль серии и является источником истины для
последующей генерации. Основной light-эталон композиции, рисовки и предметной
насыщенности —
[`welcome-hero.png`](refs/illustrations/final/light/welcome-hero.png). Эталон
идентичности кота —
[`welcome-explore2-v1.png`](refs/illustrations/experiments/02-character-calibration/welcome-explore2-v1.png).
Канонические scene-блоки финального пакета находятся в
[`illustration-generation-manifest.md`](illustration-generation-manifest.md).
Остальные изображения не становятся character reference автоматически: дизайн
каждого нового персонажа сначала проходит отдельное одобрение.

## Визуальный язык

- Взрослая продуктовая editorial-иллюстрация со сказочной интонацией.
- Простая округлая геометрия и крупные спокойные силуэты.
- Чистый тёмный контур средней толщины, слегка живой, но не эскизный.
- Матовые заливки и минимум внутренних линий.
- Сцена может содержать несколько смысловых и декоративных объектов: книги,
  листы, чайную утварь, колбы, перья, искры и абстрактные дымки.
- Дополнительная насыщенность создаётся количеством простых объектов, а не
  текстурами, штриховкой, сложным светом или детализацией внутри каждого объекта.
- Сказочность строится на предметах, которые парят, взаимодействуют невозможным
  образом или образуют свободную орбиту вокруг персонажа.
- Персонажи выглядят социальными и говорящими, но не реалистично
  человекоподобными.

Не использовать карандашную фактуру, акварельную рыхлость, реалистичный мех,
глянцевый 3D, сложный свет, детализированное concept art, орнаментальную
перегрузку и детские пропорции.

## Эталон кота

Кот взрослый, спокойный и интеллектуальный. Тело вертикальное, цельное и
округлённое, без выраженной человеческой мускулатуры. Голова простая, уши
треугольные, глаза крупные овальные. Маленькие круглые золотистые очки и тонкая
цепочка — постоянные признаки персонажа. Морда и жесты сдержанные; кот не должен
выглядеть котёнком, домашним питомцем или человеком в костюме.

Допустимо менять позу и комплекцию в небольших пределах, но сохраняются форма
головы, глаза, очки, цепочка, характер контура и взрослая манера поведения.

## Палитра

Light:

- фон — тёплый бумажный кремовый, ориентир `#FAF7F1`;
- основной тёмный — угольно-чёрный;
- акцент — насыщенный фиолетовый;
- дополнительные — светлая лаванда, приглушённый бирюзовый, немного золотистого.

Dark-адаптация foreground создаётся отдельным генеративным edit по утверждённому
режиму B. Критерии, допустимые отклонения и prompt-шаблон описаны в
[`dark-theme-adaptation.md`](dark-theme-adaptation.md). Целевой UI-фон —
глубокий сливово-чёрный `#181420`, но фон исходного PNG не перекрашивается:
удаление фона выполняется отдельным процессом.

Градиенты не являются частью языка серии. Незначительная неоднородность матовой
заливки допустима, если она не создаёт объёмный рендер.

## Композиция для UI

- Иллюстрация живёт как отдельная брендовая врезка, а не как фон страницы.
- Смысловые элементы собираются компактно; вокруг остаётся воздух для кропа.
- Для `welcome-hero` персонаж находится справа, слева свободно не менее 40–45%.
- Простая сцена содержит персонажа, сферу знаний и 4–8 второстепенных объектов.
  Они собираются в один компактный кластер и не занимают пространство интерфейса.
- Один объект остаётся одной простой графической формой. Большее количество
  предметов не должно повышать сложность контура, материалов или освещения.
- Поза на welcome-экране выражает ожидание, приветствие или приглашение, а не
  путешествие.

## Рабочий процесс генерации

1. Прикладывать утверждённый эталон персонажа как binding character and style
   reference.
   Для общей рисовки и плотности сцены прикладывать
   `refs/illustrations/final/light/welcome-hero.png`;
   для точной идентичности кота дополнительно использовать
   `welcome-explore2-v1.png`.
2. Явно перечислять сохраняемые признаки персонажа и визуального языка.
3. Описывать только новую сцену или позу; не переносить композицию эталона, если
   это не light/dark-пара.
4. Dark-версию создавать генеративным edit light-исходника по правилам
   [`dark-theme-adaptation.md`](dark-theme-adaptation.md). Кремовый фон при этом
   не менять.
5. После генерации проверять взрослый тон, плотность деталей, свободный фон,
   палитру и отсутствие случайного редизайна персонажа.

Текстовый промпт без изображения допустим для исследования вариативности, но не
для финальной серии: он близко воспроизводит общий тип кота, однако слабее
удерживает идентичность. Эталон кота также не определяет дизайн человеческих
персонажей — дед-сказитель и Иванушка требуют собственных утверждённых
character reference.

## Базовый блок промпта

```text
Use the approved reference as the binding character and illustration-style
reference. Preserve the character identity, adult demeanor, simple rounded
silhouette, medium confident slightly lively ink contour, broad matte color
shapes, very few internal lines, and restrained cream/charcoal/violet/lavender/
muted-teal/gold palette.

Create a sparse product-editorial fairytale illustration with calm intelligence
and mild playful absurdity. Keep the scene compact with generous negative space.
Use the character, the violet knowledge sphere, and a compact constellation of
4–8 simple supporting objects such as books, loose pages, tea utensils, flasks,
quills, sparks, and abstract curls. Add visual interest through the number and
arrangement of simple objects, never through textures or rendering complexity.

Avoid text, logos, childlike proportions, realistic fur, gradients, glossy 3D,
pencil texture, ornate fantasy detail, dense decoration, and highly rendered
concept-art lighting.
```

После блока добавляется описание конкретной сцены, целевого соотношения сторон и
расположения свободного пространства.

## Калибровочные материалы

- С визуальным референсом:
  [`style-test-reference-contact-sheet.png`](refs/illustrations/experiments/03-style-transfer/style-test-reference-contact-sheet.png).
- Только по текстовому паспорту:
  [`style-test-prompt-only-contact-sheet.png`](refs/illustrations/experiments/03-style-transfer/style-test-prompt-only-contact-sheet.png).
- Варианты предметной насыщенности:
  [`welcome-detail-contact-sheet.png`](refs/illustrations/experiments/04-detail-density/welcome-detail-contact-sheet.png).
- Расширенная серия и кандидаты новых персонажей:
  [`series-expanded-contact-sheet.png`](refs/illustrations/experiments/05-expanded-series/series-expanded-contact-sheet.png).
- Эксперименты адаптации к dark UI:
  [`contact-sheet-source-a-b.png`](refs/illustrations/experiments/08-dark-generative/contact-sheet-source-a-b.png).
- Утверждённые light/dark-пары:
  [`light-dark-contact-sheet.png`](refs/illustrations/final/light-dark-contact-sheet.png).
