# Агентная запись демо-материалов для README — обзор инструментов

> Ресерч под итерацию design-branding feat-005 (бренд-кит и оформление репозитория).
> Вопрос: какими инструментами LLM-агент может создавать демо-материалы (GIF, видео
> с озвучкой, терминальные записи) воспроизводимо, headless, на Linux — без ручной
> записи человеком. Прогон: 2026-08-12, web-ресерч отдельным агентом (Sonnet),
> факты по репозиториям проверены через GitHub API.

## 1. Короткая GIF-демка в шапку README (10–30 сек)

| Инструмент | Что делает | Зрелость на 2026 | Цена | Подводные камни |
|---|---|---|---|---|
| **Playwright `context.recordVideo` → ffmpeg** | Встроенная в Playwright запись видео контекста в webm, дальше конвертация в gif через `palettegen`/`paletteuse` | Стабильный API, часть основного проекта Playwright | Бесплатно | Видео финализируется только после закрытия контекста/страницы; курсор не подсвечивается, движения «роботные» без доп. библиотек |
| **Chrome DevTools screencast (`Page.startScreencast`)** | Низкоуровневый покадровый захват через CDP, кадры собираются вручную | Работает, но требует своей склейки кадров | Бесплатно | Больше кода на стороне агента, нет готового пайплайна |
| **Pagecast (MCP-сервер, `mcpware/pagecast`)** | Playwright-драйвинг + запись + автоматические cinematic pan / tooltip-zoom + two-pass ffmpeg palette-конвертация в gif/webm/mp4, пресеты под GitHub (1280×720) | Молодой проект (март 2026, 37★, MIT, активные коммиты), заточен именно под «агент записывает демо» | Бесплатно, self-hosted (`npx`) | Малое комьюнити — фиксировать версию, держать fallback на голый Playwright+ffmpeg |
| **`gif_creator` в Claude in Chrome (MCP)** | Записывает взаимодействие агента с браузером и сразу отдаёт gif | Официальный инструмент Anthropic; открытый баг: дедупликация кадров не даёт «подержать» статичный title-card ([issue #18903](https://github.com/anthropics/claude-code/issues/18903)) | Бесплатно | Ограниченный контроль над таймингом статичных сцен |
| **ghost-cursor-playwright / human-cursor / OxyMouse** | Человекоподобное движение мыши по кривым Безье вместо телепортации курсора | ghost-cursor-playwright активно форкается; остальные нишевые, но рабочие | Бесплатно | Писались для антидетект-скрапинга — скорость/джиттер подбирать под съёмку |
| **ffmpeg gif vs animated webp** | `palettegen+paletteuse` — эталонный gif; animated webp в 4–6× легче, 24-бит цвет | Обе техники зрелые | Бесплатно | GitHub не гарантированно рендерит animated webp инлайн (статичный webp — с [авг. 2025](https://github.blog/changelog/2025-08-28-added-support-for-webp-images/)); gif — единственный 100% надёжный анимированный формат в README |

**Как GitHub реально встраивает видео в README** (по [community discussion #133813](https://github.com/orgs/community/discussions/133813)): `<video>`-тег и относительные ссылки на mp4 из репозитория **не рендерятся**. Проигрываемое видео получается только через `user-attachments`-ссылки (drag-and-drop в веб-редактор issue/PR) — ручной, недокументированный механизм, непригодный для воспроизводимой пересборки. Для шапки README надёжен только **gif, закоммиченный в репозиторий**.

**Рекомендация**: Playwright-сценарий + ghost-cursor для плавности курсора → `recordVideo` (webm) → `ffmpeg palettegen+paletteuse` (цель ≤5 МБ, ~10–15 fps, ширина ≤900px). Pagecast — альтернатива «всё в одном», но из-за молодости — опциональный слой, не единственная зависимость.

## 2. Полное демо-видео (1–3 мин) с озвучкой

| Инструмент | Что делает | Зрелость на 2026 | Цена | Подводные камни |
|---|---|---|---|---|
| **Remotion + официальный Agent Skill** | React-фреймворк программного видео: композиции, титры, субтитры, переходы кодом; headless-рендер; с янв. 2026 — [официальные skills для Claude Code](https://www.remotion.dev/docs/ai/skills) | Очень активен, большое комьюнити | Source-available: бесплатно для физлиц и компаний ≤3 сотрудников | Не записывает экран сам — надстройка поверх записи |
| **editly (`mifi/editly`)** | Декларативная JSON/JS-сборка видео поверх ffmpeg | MIT, 5.4k★, но последний пуш — май 2025 | Бесплатно | Риск застоя — фиксировать версию/форкать |
| **Голый ffmpeg (`filter_complex`, `concat`, `xfade`, `subtitles`)** | Полный контроль без фреймворк-рисков | Вечнозелёный | Бесплатно | Многословно, но LLM пишут ffmpeg надёжно; минимум зависимостей |
| **Pagecast `cinematic_export`** | Авто pan/zoom между точками взаимодействия на этапе записи | См. выше | Бесплатно | Только браузерные сцены |
| **screenstudio-alt (skill)** | Headless авто-zoom на клики, ускорение простоя | Ранняя стадия, **macOS-only** | Бесплатно | Не подходит (Linux) |
| **OpenScreen** | Заявлен как OSS-аналог Screen Studio | Подозрительная траектория: создан окт. 2025, ~40k★, уже archived — похоже на накрутку | — | Не использовать без проверки |
| **auto-editor** | CLI-вырезание тишины/простоя по громкости | Зрелый | Бесплатно | Полезен для чистки записи и голоса |

**Ключевой вывод**: раз демо ставит и записывает агент, точные координаты кликов и тайминги уже есть в Playwright-сценарии — эвристический «авто-zoom» не нужен, координаты прокидываются напрямую в `ffmpeg zoompan`/Remotion-композицию (или Pagecast, который их и так знает).

**TTS для русского**:

| Сервис | Позиция 2026 | Цена | Комментарий |
|---|---|---|---|
| **ElevenLabs** | Лидер по естественности (MOS ≈ 4.14), мультиязычность, [Forced Alignment](https://elevenlabs.io/docs/overview/capabilities/forced-alignment) — word-level таймкоды к готовому тексту | Платный API | Лучший русский + точные тайминги субтитров без ASR |
| **OpenAI TTS** | Ниже по естественности, сильнее в steerability | ~$0.015/1000 симв. | Fallback при ограниченном бюджете |
| Cartesia, Hume, Gemini TTS, CosyVoice2 | Ниши (латентность, эмоции, self-hosted) | Разное | Для русского не лидеры |

**Субтитры**: текст озвучки — наш собственный сценарий, поэтому не Whisper по аудио, а word-level таймкоды прямо от TTS (ElevenLabs Forced Alignment) → сборка `.srt` → `ffmpeg -vf subtitles=...`.

**Оверлей веб-камеры («кружочек» спикера)**: ffmpeg `overlay` + альфа-маска круга — готовые рецепты есть. Живого спикера агент не сгенерирует: либо человек записывает свой фрагмент, а агент вклеивает, либо слой заменяется анимированной плашкой/лого через Remotion.

**Рекомендация**: Playwright/Pagecast (сцены UI) → auto-editor (чистка простоев) → ElevenLabs (озвучка + таймкоды) → Remotion либо ffmpeg (композиция, титры, субтитры). Remotion — если нужна полировка и лицензия ок (free tier покрывает); минимум — ffmpeg `concat`+`subtitles`.

## 3. Терминальная запись установки (self-hosted гайд)

| Инструмент | Что делает | Зрелость на 2026 | Цена | Подводные камни |
|---|---|---|---|---|
| **VHS (`charmbracelet/vhs`)** | Декларативный `.tape`-файл (`Type`, `Sleep`, `Enter`) → детерминированный рендер в gif/mp4/webm через ttyd+ffmpeg; `vhs record` генерирует tape из живой сессии | Очень активен, 20.6k★, MIT | Бесплатно | Требует ttyd + ffmpeg; рендер через веб-рендер ttyd (для gif неотличимо) |
| **asciinema + agg** | Запись asciicast реального pty + конвертация в gif (gifski) | Оба зрелые, пуши июль 2026, GPL-3.0 | Бесплатно | Нет декларативного скрипт-формата — сценарий оборачивать в bash с `sleep` |
| **terminalizer** | YAML-конфиг записи + gif | 16k★, последний пуш авг. 2024 — заброшен | Бесплатно | Не рекомендуется |

**Рекомендация**: **VHS** — `.tape`-файл коммитится в репозиторий как код, прогон детерминирован, идеально для агента. asciinema+agg — запасной вариант, если нужен интерактивный плеер на doc-странице.

## Сводный рекомендованный стек

```
Артефакт 1 (header GIF):
  Playwright (+ ghost-cursor-playwright) → recordVideo (webm)
    → ffmpeg palettegen/paletteuse → demo.gif в репозитории

Артефакт 2 (демо-видео 1–3 мин):
  Playwright/Pagecast (сцены UI, pan/zoom) → auto-editor (чистка)
    → ElevenLabs TTS (RU) + Forced Alignment (таймкоды → .srt)
    → Remotion или ffmpeg filter_complex (композиция + титры + субтитры)
    → mp4 на YouTube; в README — кликабельный thumbnail со ссылкой
      (GitHub не рендерит mp4 инлайн из репозитория)

Артефакт 3 (установка в терминале):
  VHS .tape-файл в репозитории → vhs run install.tape → install.gif
```

Каждый шаг воспроизводим одной командой (`make demo-gif`, `make demo-video`, `make install-gif` — ложится в Makefile-подход проекта), headless CLI на Linux; платный компонент один — TTS API.

**Трудоёмкость для агента**: артефакт 1 — низкая (один Playwright-скрипт + ffmpeg-пайплайн; риск — подбор веса gif); артефакт 3 — низкая (`.tape` пишется как shell-скрипт); артефакт 2 — средняя-высокая (многошаговый пайплайн, платный TTS, синхронизация аудио/видео/субтитров) — отдельная итерация, предварительно решить лицензию Remotion и бюджет ElevenLabs.

## Источники

- [Playwright — Videos](https://playwright.dev/docs/videos)
- [Pagecast (MCP, mcpware)](https://github.com/mcpware/pagecast)
- [ghost-cursor-playwright](https://github.com/DKprofile/ghost-cursor-playwright/)
- [human-cursor (CloverLabsAI)](https://github.com/CloverLabsAI/human-cursor)
- [GitHub Community Discussion #133813 — embedding video via relative path](https://github.com/orgs/community/discussions/133813)
- [GitHub Changelog — WebP images support (2025-08-28)](https://github.blog/changelog/2025-08-28-added-support-for-webp-images/)
- [screenstudio-alt (Claude Code skill, macOS-only)](https://github.com/connerkward/screenstudio-alternative-skill)
- [Remotion — Agent Skills docs](https://www.remotion.dev/docs/ai/skills)
- [Remotion License](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)
- [editly (mifi)](https://github.com/mifi/editly)
- [ElevenLabs — Forced Alignment](https://elevenlabs.io/docs/overview/capabilities/forced-alignment)
- [Voice Generation Models Compared 2026 (SurePrompts)](https://sureprompts.com/blog/voice-generation-models-compared-2026)
- [VHS (charmbracelet)](https://github.com/charmbracelet/vhs)
- [asciinema/agg](https://github.com/asciinema/agg) · [asciinema](https://github.com/asciinema/asciinema)
- [terminalizer (заброшен)](https://github.com/faressoft/terminalizer)
- [Claude in Chrome gif_creator — баг дедупликации кадров](https://github.com/anthropics/claude-code/issues/18903)
