# Managed-сервисы удаления фона — исследование

Исследование сторонних managed-решений (облачные API и онлайн-инструменты) для
удаления фона под наш конкретный кейс: брендовые векторно-стилизованные
иллюстрации (flat editorial, плоские заливки, чистый контур, сказочный стиль),
~1.5–1.7 Мп, кремовый фон `#FAF7F1`. Поводом стал тупик локальных методов —
детерминированный `color-to-alpha` не режет замкнутые внутренние области, а
локальный ML (rembg U²-Net/IS-Net) теряет мелочь и оставляет тёмные пятна;
BiRefNet general-lite не влезает в память этой машины. Подробности локального
бенчмарка — в [`transparent-png-research.md`](transparent-png-research.md).

Данные верифицированы по официальным страницам сервисов; цены и лимиты актуальны
на июнь 2026 и со временем меняются.

## Главный вывод

**Победитель для разовой обработки — managed BiRefNet, бесплатно через
официальный Hugging Face Space автора модели** (`ZhengPeng7/BiRefNet_demo`),
веса **General-HR @ 2048**. На наших картинках он дал околоидеальный результат:
чистая альфа без кремового halo (одинаково ложится на светлый и тёмный UI) и
корректно вырезанные внутренние замкнутые области. Готовые примеры лежат в
[`refs/illustrations/managed-service-examples/`](refs/illustrations/managed-service-examples/).

Для продакшен-масштаба (batch/API, до ~50 картинок) — те же семейства моделей
через платный хостинг по центам за прогон: **fal.ai BiRefNet v2** (потолок 2048,
`refine_foreground`) или **Replicate** (RMBG-2.0 / BiRefNet / InSPyReNet под
единым API).

**Центральное предупреждение исследования:** ни один источник не подтверждает
качество на нашем конкретном стиле. Обучающая выборка RMBG-2.0 на **87.70%**
фотореалистична и лишь на **12.30%** не-фотореалистична, то есть
illustration/cartoon — меньшинство распределения. «Чистый край» и «вырезание
внутренних дырок» провайдеры заявляют только в общем смысле. Поэтому пригодность
устанавливается только эмпирически — что мы и сделали через бесплатный HF Space.

## Архитектурный контекст: BiRefNet и RMBG-2.0 — родственники

RMBG-2.0 построен на архитектуре **BiRefNet** (Bilateral Reference Framework для
high-resolution dichotomous image segmentation), усиленной проприетарным
датасетом и схемой обучения Bria. Оба выдают **одноканальную 8-битную grayscale
альфу с 256 уровнями прозрачности** (не бинарную маску) — это прямо релевантно
мягким краям (дымки, искры, борода) и чистому стыку с любым фоном. Выбор между
ними — это в первую очередь датасет/тюнинг, а не разная архитектура.

Источники: model card [RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0),
[fal.ai BiRefNet v2](https://fal.ai/models/fal-ai/birefnet/v2).

## Сравнение кандидатов

| Сервис | Модель | Цена | Макс. разрешение | Privacy | Пригодность под наш кейс |
|---|---|---|---|---|---|
| **HF Space `ZhengPeng7/BiRefNet_demo`** | BiRefNet (15 чекпойнтов: General, General-HR, Matting, Matting-HR, …) | **бесплатно** (ZeroGPU) | до 2048 | браузерная загрузка | **Победитель.** Бесплатный способ сразу проверить оба критичных требования. Caveat: ZeroGPU иногда в очереди/спит |
| **fal.ai BiRefNet v2** | BiRefNet (Light/Heavy/Portrait + Matting/HR) | по прогону | **до 2048×2048 (~4 Мп)** | opt-out не верифицирован | Сильный production-кандидат: потолок 2048 покрывает наши ~1.57 Мп без даунскейла; `refine_foreground` целится в очистку цветового spill по краю |
| **fal.ai Bria RMBG-2.0** | RMBG-2.0 | $0.018 (~55/$1) | **до 1024** (исходник даунскейлится) | opt-out не верифицирован | Минус: наши 1448×1086 / 1672×941 > 1024 → даунскейл перед обработкой, край считается на уменьшенной картинке |
| **Replicate `bria/remove-background`** | RMBG-2.0 | по прогону | — | сроки хранения размыты | 256-уровневая альфа; удобно для A/B всех трёх архитектур через единый API |
| **Replicate `851-labs/background-remover`** | InSPyReNet (`transparent-background`) | **$0.00049 (~2040/$1)** | — | сроки хранения размыты | Самый дешёвый general-purpose; другая семья моделей — дешёвый бейзлайн в A/B, не проверен на сложных краях |
| **Photoroom API** | проприетарная | $0.02 (Basic) | HD на Plus | **не хранит и не обучается** на API-картинках | Лучшая позиция по privacy (SOC 2 / GDPR); архитектура закрыта — поведение на нашем стиле непредсказуемо |
| **remove.bg API** | проприетарная | 50 вызовов/мес free | до 10 Мп PNG / 50 Мп WebP | удаление обычно в течение 60 мин; improvement program с opt-out | Удобный бесплатный объём для A/B всего пака |
| **Pixian.AI** | не раскрыта | ~€0.0019 за наши ~1.5 Мп (по мегапикселям) | до 25 Мп | — | Дёшево, но архитектура и качество на иллюстрациях не подтверждены |

Лицензия: RMBG-2.0 — CC BY-NC 4.0 (некоммерческий self-host; коммерческий требует
соглашения с Bria). При вызове **через хостинг** (fal.ai/Replicate) коммерческий
аспект уже покрыт провайдером.

## Чего исследование НЕ покрыло

Верифицированных утверждений не осталось по: Clipdrop, Adobe (Express/Firefly
Services), Slazzer, Cutout.pro, Erase.bg/Pixelbin, PhotoScissors, Picsart API,
Vance AI, Cloudinary AI background removal, Hugging Face Inference Endpoints. Их
цены/лимиты/privacy не подтверждены — сравнивать на равных нельзя.

## Метод-вывод (паттерн на будущее)

**Hugging Face Spaces — сильный приём для разовых специфических задач.** Кто-то
уже развернул SOTA-модель с веб-загрузкой; доступ бесплатный (ZeroGPU) или по
дешёвой подписке (~$9/мес HF Pro за бо́льшие квоты/приоритет). Для узких задач,
где локальный путь упирается в память или качество, а полноценная интеграция API
избыточна, это кратчайший путь к SOTA-результату без капитальных вложений. Стоит
держать как стандартную опцию для подобных разовых обработок.

## Источники

- [HF Space BiRefNet demo](https://huggingface.co/spaces/ZhengPeng7/BiRefNet_demo)
- [fal.ai BiRefNet v2](https://fal.ai/models/fal-ai/birefnet/v2) · [fal.ai BiRefNet](https://fal.ai/models/fal-ai/birefnet)
- [fal.ai Bria RMBG-2.0](https://fal.ai/models/fal-ai/bria/background/remove)
- [Replicate bria/remove-background](https://replicate.com/bria/remove-background) · [851-labs/background-remover](https://replicate.com/851-labs/background-remover) · [коллекция](https://replicate.com/collections/remove-backgrounds)
- [RMBG-2.0 model card](https://huggingface.co/briaai/RMBG-2.0)
- [Photoroom API pricing](https://docs.photoroom.com/remove-background-api-basic-plan/pricing) · [Photoroom: обучается ли AI на ваших изображениях](https://help.photoroom.com/en/articles/10067660-does-the-ai-learn-from-your-images)
- [remove.bg privacy](https://www.remove.bg/b/prioritizing-security-and-privacy-at-remove-bg) · [Replicate privacy](https://replicate.com/privacy)
- [Pixian.AI pricing](https://pixian.ai/pricing)
