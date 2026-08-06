# Managed background removal — победивший подход

Эти PNG — результат прохода исходной иллюстрации через managed-модель
**BiRefNet, веса `General-HR`**, бесплатный официальный Hugging Face Space автора
модели: <https://huggingface.co/spaces/ZhengPeng7/BiRefNet_demo>.

Это итоговый практический подход итерации к прозрачным cutout: качество близко к
идеалу на нашем плоском сказочном стиле — чистая альфа без кремового halo (ровно
ложится и на светлый, и на тёмный UI `#181420`) и корректно вырезанные замкнутые
внутренние области (просветы между объектами, петли ручек). Это решает обе
проблемы, на которых застряли локальные методы (см.
[`../../../transparent-png-research.md`](../../../transparent-png-research.md) и
[`../../../background-removal-services-research.md`](../../../background-removal-services-research.md)).

## Файлы

| Файл | Сцена | Веса | Разрешение инференса |
|---|---|---|---|
| `empty-artifacts__birefnet-general-hr-2048.png` | empty-artifacts | BiRefNet General-HR | 2048×2048 |
| `empty-artifacts__birefnet-general-hr-2048x1536.png` | empty-artifacts | BiRefNet General-HR | 2048×1536 (нативные пропорции) |

Обе версии дали околоидеальный результат; вариант с инференсом в нативных
пропорциях `2048×1536` чуть ровнее по тонким краям. Остаются лишь мелкие
артефакты, добиваемые лёгкой постобработкой.

## Воспроизведение

1. Открыть Space <https://huggingface.co/spaces/ZhengPeng7/BiRefNet_demo>.
2. Выбрать веса `General-HR`.
3. Загрузить исходник из `../final/light/` или `../final/dark/`.
4. Выставить разрешение инференса 2048 (квадрат) либо нативные пропорции
   с длинной стороной 2048 — для нашего ~1.57 Мп исходника даунскейла нет.
5. Скачать прозрачный PNG.

Продакшен-масштаб (batch/API) — те же семейства моделей через хостинг: fal.ai
BiRefNet v2 (потолок 2048, `refine_foreground`) или Replicate
(RMBG-2.0 / BiRefNet / InSPyReNet). Сравнение — в research-доке итерации.
