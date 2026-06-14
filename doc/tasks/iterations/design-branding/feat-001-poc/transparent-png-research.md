# Удаление фона из брендовых иллюстраций

Цель исследования — автоматически удалить кремовый фон из light- и
dark-иллюстраций без ручных масок, сохранив светлые страницы, одежду, стекло,
перья, искры, лавандовые дымки и мягкие края.

Среди **локальных** методов практический benchmark показал, что лучше всего
работает не ML-сегментация, а детерминированный `color-to-alpha`: фон
определяется по границе изображения, после чего удаляются только связанные с
границей области. По итогам визуального ревью на полном паке как лучший локальный
fallback оставлены два кандидата: `soft-balanced` и `soft-wide`.

Однако у локального подхода остались два нерешённых дефекта — кремовый halo на
тёмном фоне `#181420` и невырезанные **замкнутые внутренние области** (фон по
связности с границей физически не режет петли ручек и просветы между объектами).
Итоговое практическое решение этих проблем найдено вне локального пути — в
managed-модели **BiRefNet (веса General-HR)**, бесплатно через Hugging Face
Space; см. [`background-removal-services-research.md`](background-removal-services-research.md)
и готовые примеры в
[`refs/illustrations/managed-service-examples/`](refs/illustrations/managed-service-examples/).
Раздел ниже фиксирует именно локальный benchmark.

## Что проверено

В benchmark вошли light- и dark-версии трёх сцен:

- `welcome-hero.png`;
- `empty-sphere.png`;
- `empty-artifacts.png`.

Всего выполнено 78 запусков:

- ImageMagick: exact match и `fuzz` 2%, 4%, 6%;
- soft `color-to-alpha`: три набора порогов;
- те же три маски с foreground decontamination;
- PyMatting `estimate_alpha_knn`;
- `rembg` с U²-Net и IS-Net Anime на CPU.

Все исходники имеют разрешение около 1,6 Мп. Их фон не однотонный: значения по
углам лежат примерно в диапазоне RGB `(248–253, 232–243, 215–228)`. Light- и
dark-версии используют почти одинаковый кремовый фон.

Артефакты эксперимента:

- [light contact sheet](refs/illustrations/experiments/09-background-removal/contact-sheet-methods-light.jpg);
- [dark contact sheet](refs/illustrations/experiments/09-background-removal/contact-sheet-methods-dark.jpg);
- [увеличенные края](refs/illustrations/experiments/09-background-removal/contact-sheet-edge-crops.jpg);
- [manifest всех запусков](refs/illustrations/experiments/09-background-removal/manifest.json);
- [сводка метрик](refs/illustrations/experiments/09-background-removal/metrics-summary.csv);
- [воспроизводимые скрипты](refs/illustrations/experiments/09-background-removal/tools/).

## Результат

| Метод | Среднее время | Средний MAE recomposite | Визуальный результат |
|---|---:|---:|---|
| ImageMagick `fuzz 2%` | 0,60 с | 0,479 | Остаются кремовые края и шум |
| ImageMagick `fuzz 4%` | 0,60 с | 0,567 | Начинает вырезать страницы и светлые области |
| ImageMagick `fuzz 6%` | 0,60 с | 0,728 | Заметно разрушает светлые детали |
| Soft, tight | 0,08 с | 0,482 | Сохраняет детали, но оставляет примесь фона в edge RGB |
| Soft, balanced | 0,08 с | 0,513 | Хорошая маска, но на тёмном фоне заметен halo |
| **Decontam, balanced** | **0,18 с** | **0,587** | **Лучший общий баланс: чистые края и сохранённые детали** |
| PyMatting KNN | 4,76 с | 0,822 | Слишком много partial alpha, края становятся мягче и мутнее |
| U²-Net | 0,94 с | 14,239 | Оставляет кремовые острова, теряет эффекты, меняет края |
| IS-Net Anime | 2,03 с | 20,231 | Теряет большую часть светлых объектов и композиции |

MAE/RMSE оценивают восстановление исходной картинки при обратной композиции на
оценённый кремовый фон. Они полезны для поиска грубых разрушений, но не измеряют
качество прозрачности. Например, exact match имеет нулевой MAE, хотя оставляет
почти весь фон. Финальный выбор сделан по contact sheets на `#181420`, чёрном,
белом и кремовом фоне.

## Финальные кандидаты

После первичного benchmark `decontam-balanced` рассматривался как технический
фаворит из-за очистки кремовой примеси в edge RGB. Визуальное ревью показало,
что decontamination местами делает края слишком жёсткими или тёмными. Поэтому
он не вошёл в финальную пару.

На всех 12 light/dark-файлах подготовлены:

- `soft-balanced` с порогами `8/28`;
- `soft-wide` с порогами `12/42`.

Оба candidate-пака и восемь contact sheets находятся в
[`refs/illustrations/candidates/transparent/`](refs/illustrations/candidates/transparent/).
Они ожидают аппрува архитектора.

`soft-balanced` бережнее к светлым краям. `soft-wide` сильнее очищает внешний
фон и визуально предпочтительнее вокруг дымок и искр, но требует проверки
страниц, одежды, бороды и печи в реальном UI.

## Как работает soft color-to-alpha

Алгоритм использует выбранную пару RGB-distance:

```text
border pixels
      ↓
robust median background color
      ↓
candidate pixels with distance < high threshold
      ↓
only regions connected to image border
      ↓
soft alpha between low and high threshold
```

Связность с границей принципиальна. Без неё страницы, светлая одежда и блики,
цвет которых близок к фону, превращаются в отверстия.

Текущие пороги подходят всем 12 финальным изображениям, но не считаются
универсальными для будущих генераций. Перед пакетной обработкой нового набора
нужно проверить border color distribution и contact sheet.

## ImageMagick

Проверена команда:

```bash
magick input.png \
  -alpha on \
  -fuzz 4% \
  -transparent "#fbeedf" \
  output.png
```

Метод быстрый и удобный для baseline, но выдаёт бинарную alpha без корректного
восстановления edge RGB. При малом `fuzz` остаётся светлая кайма, при большом
начинают исчезать книги, страницы и одежда. В production pipeline его стоит
оставить только как диагностический контроль.

## PyMatting

Использован PyMatting `1.1.15`, `estimate_alpha_knn`. Полноразмерный matting для
шести изображений нерационален по памяти, поэтому вход уменьшался до 800 px по
длинной стороне, а matte затем масштабировался обратно.

Весь детерминированный прогон занял 3 мин 33 с и достиг пикового RSS около
1,75 ГБ. Сам PyMatting в среднем тратил 4,76 с на изображение после прогрева.
Downscale сделал края мягче, а доля partial alpha выросла до 19,7%. Для этих
плоских иллюстраций это ухудшение относительно `decontam-balanced`.

PyMatting может быть полезен для фотографий, волос или сложной полупрозрачности,
но не нужен в основном pipeline текущего пака.

## CPU ML без GPU

Локальный запуск реален. Benchmark выполнен в изолированном Python 3.12
окружении:

| Компонент | Версия |
|---|---|
| `rembg` | 2.0.76 |
| `onnxruntime` | 1.26.0 |
| Pillow | 12.2.0 |
| NumPy | 2.4.6 |
| PyMatting | 1.1.15 |

U²-Net и IS-Net Anime занимают по 176 МБ, вместе 336 МБ. Полный запуск двух
моделей на шести изображениях, включая загрузку второго веса, занял 1 мин 24 с.
Пиковый RSS процесса составил около 2,0 ГБ. После инициализации U²-Net обрабатывал
изображение в среднем за 0,94 с, IS-Net Anime — за 2,03 с.

Модели технически подходят для ноутбука без GPU, но семантически не подходят
этим сценам. Они ищут единый foreground-объект, тогда как композиция состоит из
разрозненных книг, искр, дыма и колб. IS-Net Anime особенно агрессивно удаляет
светлые элементы. ML можно использовать только как дополнительный prior для
фотографий, не как основной способ обработки этого пака.

Checksums использованных весов:

```text
u2net.onnx       8d10d2f3bb75ae3b6d527c77944fc5e7dcd94b29809d47a739a7a728a912b491
isnet-anime.onnx f15622d853e8260172812b657053460e20806f04b9e05147d49af7bed31a6e99
```

## Облачные сервисы

Условия проверены по официальным страницам 13 июня 2026 года. Сами изображения
не отправлялись: в рабочем окружении нет API-ключей, а качество сервиса без
фактического A/B-теста не подтверждено.

| Сервис | Бесплатное использование | Ограничения и автоматизация | Privacy и пригодность |
|---|---|---|---|
| **remove.bg API** | Первые 50 API-вызовов в месяц | До 10 Мп для прозрачного PNG, до 50 Мп для WebP/ZIP; batch/API; текущая платная цена с динамической pricing page не подтверждена | Передача изображения облаку; участие изображения в improvement program предлагается отдельно и допускает отказ. Лучший бесплатный кандидат для A/B-теста всего пака |
| **Photoroom API** | 10 Basic images в месяц; до 1000 sandbox calls для Image Editing API | Remove Background API указан по `$0.02` за изображение, Plus — `$0.10`; есть API и dashboard | Официальная privacy policy прямо исключает изображения, обработанные через API, из model improvement. Лучший документированный production-кандидат |
| **Clipdrop** | Web-инструмент заявлен бесплатным, до `5000×5000` | Допускает несколько изображений; старый API перенесён в Jasper, публичную актуальную цену подтвердить не удалось | Детальная retention policy на доступной странице не раскрылась. Для воспроизводимого pipeline условия сейчас недостаточно прозрачны |
| **Adobe Express** | Бесплатно, без карты и без обязательного аккаунта для старта | JPEG/PNG/WebP до 40 МБ, результат PNG; на странице нет batch/API-контракта | Подходит для ручной контрольной пробы, но не для автоматического пакетного процесса |

Этот раздел — предварительный обзор. Полное исследование managed-сервисов (под
капотом модели, цены, лимиты, privacy) и фактический бесплатный A/B вынесены в
отдельный док [`background-removal-services-research.md`](background-removal-services-research.md).
По его итогам выбран и проверен на наших картинках managed **BiRefNet General-HR**
через бесплатный Hugging Face Space — он закрыл и halo, и внутренние дырки.

## Итог и следующий шаг

Практический итог итерации: для прозрачных cutout используется managed
**BiRefNet General-HR** (бесплатно через HF Space) — он единственный закрыл оба
дефекта локального пути (halo на тёмном фоне и замкнутые внутренние области).
`soft-balanced` / `soft-wide` остаются как локальный детерминированный fallback,
если managed-проход недоступен. Подробности и production-варианты (fal.ai /
Replicate) — в [`background-removal-services-research.md`](background-removal-services-research.md).

Дальнейшие шаги:

1. Прогнать оставшиеся сцены через BiRefNet General-HR (или batch-хостинг при
   масштабировании) и собрать production transparent-пак.
2. Лёгкая постобработка для добивания мелких артефактов края.
3. Только затем запускать SVG benchmark.

Не следует сразу векторизовать текущие изображения: SVG benchmark должен
получить на вход уже утверждённый прозрачный PNG, иначе дефекты маски превратятся
в лишние paths.

## Воспроизведение

Изолированное окружение не меняет зависимости проекта:

```bash
uv venv --python python3.12 /tmp/lf-bg-benchmark-venv
uv pip install --python /tmp/lf-bg-benchmark-venv/bin/python \
  pillow numpy scipy pymatting psutil "rembg[cpu]"

/tmp/lf-bg-benchmark-venv/bin/python \
  refs/illustrations/experiments/09-background-removal/tools/benchmark.py \
  deterministic

U2NET_HOME=/tmp/lf-bg-models \
/tmp/lf-bg-benchmark-venv/bin/python \
  refs/illustrations/experiments/09-background-removal/tools/benchmark.py \
  ml --models u2net isnet-anime

/tmp/lf-bg-benchmark-venv/bin/python \
  refs/illustrations/experiments/09-background-removal/tools/build_candidates.py
```

Команды запускаются из директории текущей итерации либо с полными путями из
корня репозитория. Скрипт не изменяет `final/light` и `final/dark`.

## Источники

- [remove.bg API](https://www.remove.bg/api)
- [remove.bg pricing](https://www.remove.bg/pricing)
- [remove.bg privacy](https://www.remove.bg/privacy)
- [Clipdrop Remove Background](https://clipdrop.co/remove-background)
- [Clipdrop API migration](https://clipdrop.co/apis)
- [Photoroom API pricing](https://www.photoroom.com/api/pricing)
- [Photoroom privacy](https://www.photoroom.com/legal/privacy)
- [Adobe Express Background Remover](https://www.adobe.com/express/feature/image/remove-background)
- [rembg](https://github.com/danielgatis/rembg)
- [PyMatting](https://github.com/pymatting/pymatting)
- [ImageMagick masks](https://usage.imagemagick.org/masking/)

Firecrawl был аутентифицирован, но на момент исследования имел `0 / 1,000`
credits. Поэтому официальные страницы сервисов прочитаны через резервный
web-доступ. Динамические или недоступные значения явно оставлены
неподтверждёнными.
