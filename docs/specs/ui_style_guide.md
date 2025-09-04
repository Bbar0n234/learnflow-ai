# LearnFlow AI — UI Style Guide v0.1

> Базовые соглашения по визуальному стилю и токенам дизайна для веб‑приложения (React + Tailwind). Фокус: чтение/правка конспектов, академичный вайб, спокойствие и уверенность. Русскоязычная аудитория, default‑dark.

---

## 1) Бренд‑личность и принципы

**Ключевые ассоциации:** академичность, системность, «спокойный интеллект», практичность, доверие.

**Тон UI:** сухой, ясный, без «игривости». Микрокопия — короткая, ориентирована на действие.

**Принципы:**

* **Читаемость > украшательства.** Основная задача — быстро понимать структуру материалов.
* **Низкий визуальный шум.** Ограниченное число цветов/теней, аккуратные границы.
* **Акцент на иерархии.** Контраст, размер, расстояние — первичные инструменты.
* **Доступность по умолчанию.** Контрасты ≥ 4.5:1 для текста.
* **Default Dark.** Ночью/в общежитии чаще темный экран; уважаем `prefers-color-scheme`.

---

## 2) Цветовая система

Палитра построена вокруг «академического индиго» + акцентной бирюзы для действий. Нейтрали — холодные.

### 2.1 Базовые токены (семантические)

* `--color-bg`: фон основного слоя
* `--color-elev`: фон карточек/панелей (elevation)
* `--color-ink`: основной текст
* `--color-muted`: вторичный текст/иконки
* `--color-border`: линии/делители
* `--color-primary`: акцент/кнопки действия
* `--color-primary-ink`: текст на акценте
* `--color-info`, `--color-success`, `--color-warn`, `--color-danger`: статусы
* `--focus-ring`: обводка фокуса

### 2.2 Светлая/темная темы (hex)

**Dark (default):**

* `--color-bg`: `#0E1116`
* `--color-elev`: `#151923`
* `--color-ink`: `#E7EAF0`
* `--color-muted`: `#9AA3B2`
* `--color-border`: `#242B38`
* `--color-primary`: `#6A7BFF` (индиго‑сине‑фиолетовый)
* `--color-primary-ink`: `#0E1116`
* `--color-info`: `#3CA6FF`
* `--color-success`: `#37D399`
* `--color-warn`: `#F4C152`
* `--color-danger`: `#FF7676`
* `--focus-ring`: `#6A7BFF`

**Light:**

* `--color-bg`: `#FFFFFF`
* `--color-elev`: `#F5F7FB`
* `--color-ink`: `#0E1116`
* `--color-muted`: `#5A6474`
* `--color-border`: `#D8DEE9`
* `--color-primary`: `#4A5CFF`
* `--color-primary-ink`: `#FFFFFF`
* `--color-info`: `#1479E9`
* `--color-success`: `#1EAD7F`
* `--color-warn`: `#C7901E`
* `--color-danger`: `#D84B4B`
* `--focus-ring`: `#4A5CFF`

**Примечания:**

* Основной акцент — индиго: не «телеграм‑синий», чтобы не путать с мессенджером.
* Статусные цвета приглушены, чтобы не конкурировать с учебным контентом.

---

## 3) Типографика

### 3.1 Гарнитуры (Cyrillic‑ready)

* **UI/Body:** *Inter* (fallback: `system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial, "Apple Color Emoji", "Segoe UI Emoji"`)
* **Заголовки/Нарратив в конспектах:** *Manrope* — немного более «человечная» геометрия.
* **Моно (формулы/кодовые блоки/LaTeX preview):** *JetBrains Mono*

### 3.2 Иерархия и размеры

* `h1`: 28–32 / 36–40, 700, -2% letter‑spacing
* `h2`: 22–24 / 30–32, 700
* `h3`: 18–20 / 26–28, 600
* `body-lg`: 16 / 24, 500
* `body`: 15 / 22, 400 (основной текст конспекта)
* `caption`: 12 / 16, 500 (подписи, лейблы)

**Формулы/математика:** не делать кегль меньше 15px; межстрочный ≥ 1.4; контраст высокий.

---

## 4) Пространство, радиусы, тени

### 4.1 Шкала отступов (px)

`4, 8, 12, 16, 20, 24, 32, 40, 48, 64`

### 4.2 Радиусы

* `--radius-xs: 6px` (inputs, chips)
* `--radius-sm: 10px` (карточки)
* `--radius-md: 14px` (модальные, крупные кнопки)

### 4.3 Тени (лаконичные)

* `--shadow-sm`: 0 1px 0 0 rgba(0,0,0,0.25)
* `--shadow-md`: 0 6px 18px -8px rgba(0,0,0,0.35)
* `--shadow-lg`: 0 18px 32px -12px rgba(0,0,0,0.45)

Elevation использовать умеренно: карточки/панели редактирования.

---

## 5) Состояния и интеракции

* **Hover:** лёгкое повышение яркости + тень на `elev`.
* **Active/Pressed:** сдвиг -1px по Y, тень уменьшается.
* **Focus:** 2px внешнее кольцо `--focus-ring`, offset 2px (доступность).
* **Disabled:** `opacity: 0.5`, курсор `not-allowed`.

---

## 6) Компонентные паттерны (визуальные правила)

### 6.1 Кнопки

* **Primary:** заполненная `--color-primary` c текстом `--color-primary-ink`.
* **Secondary:** заливка `--color-elev`, текст `--color-ink`, бордер `--color-border`.
* **Ghost:** прозрачная, без бордера, для второстепенных действий.
* **Danger:** заливка `--color-danger`.
* Размеры: sm (28/8×12), md (36/12×16), lg (44/12×20); радиус `--radius-xs`.

### 6.2 Инпуты/текстарии

* Фон `--color-elev`, текст `--color-ink`, плейсхолдер = `--color-muted`.
* Бордер `1px --color-border`, при фокусе `2px --focus-ring` (outline‑style), без смещения layout.

### 6.3 Карточки/панели

* Фон `--color-elev`, бордер `--color-border`, тень `--shadow-sm`.
* Заголовок h3, подзаголовок `body` muted, контент — сетка с 16–24px gap.

### 6.4 Теги/чипы

* Радиус `--radius-xs`, высота 24–28px, паддинги 8–10px.
* Варианты: default (elev/bg), success/warn/danger/info — `background: color @12%`, `text: @100%`.

### 6.5 Алёрты/баннеры статусов

* Левый цветной бордер 3px по статусу, мягкий фон @10–12%.

### 6.6 Таблицы/списки

* Чередование рядов `rgba(255,255,255,0.02)` в dark.
* Sticky header, разделители `--color-border`.

### 6.7 Редактор (инлайн‑правки)

* Выделение редактируемых фрагментов: заливка `--color-primary` @12% + dotted underline.
* Панель действий (pop‑over): карточка с тенью `--shadow-md`, кнопки ghost.

---

## 7) Сетки и брейкпоинты

* Контентная ширина: 1200px max, 24px гуттер мобайл, 32–40px десктоп.
* Брейкпоинты: 480 / 768 / 1024 / 1280 / 1536.
* Основные шаблоны: 12‑колонок десктоп, 6 — планшет, 4 — мобайл.

---

## 8) Анимации/движение

* Базовая длительность: 150–200ms; easing: `cubic-bezier(0.2, 0.8, 0.2, 1)`.
* Редакторские всплывашки: fade+scale 98%→100%, 120ms.
* Списки/конспекты: анимируем только появление, не скролл.

---

## 9) Токены как CSS‑переменные

```css
:root {
  /* Light (fallback) */
  --color-bg: #FFFFFF;
  --color-elev: #F5F7FB;
  --color-ink: #0E1116;
  --color-muted: #5A6474;
  --color-border: #D8DEE9;
  --color-primary: #4A5CFF;
  --color-primary-ink: #FFFFFF;
  --color-info: #1479E9;
  --color-success: #1EAD7F;
  --color-warn: #C7901E;
  --color-danger: #D84B4B;
  --focus-ring: #4A5CFF;

  --radius-xs: 6px;
  --radius-sm: 10px;
  --radius-md: 14px;

  --shadow-sm: 0 1px 0 0 rgba(0,0,0,0.06);
  --shadow-md: 0 6px 18px -8px rgba(0,0,0,0.10);
  --shadow-lg: 0 18px 32px -12px rgba(0,0,0,0.14);
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0E1116;
    --color-elev: #151923;
    --color-ink: #E7EAF0;
    --color-muted: #9AA3B2;
    --color-border: #242B38;
    --color-primary: #6A7BFF;
    --color-primary-ink: #0E1116;
    --color-info: #3CA6FF;
    --color-success: #37D399;
    --color-warn: #F4C152;
    --color-danger: #FF7676;
    --focus-ring: #6A7BFF;

    --shadow-sm: 0 1px 0 0 rgba(0,0,0,0.25);
    --shadow-md: 0 6px 18px -8px rgba(0,0,0,0.35);
    --shadow-lg: 0 18px 32px -12px rgba(0,0,0,0.45);
  }
}

html, body {
  background: var(--color-bg);
  color: var(--color-ink);
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, "Noto Sans", Arial, "Apple Color Emoji", "Segoe UI Emoji";
}
```

---

## 10) Tailwind настройка (фрагмент)

```ts
// tailwind.config.ts
export default {
  darkMode: 'class', // вручную через .dark на <html>; можно переключать по toggle
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        elev: 'var(--color-elev)',
        ink: 'var(--color-ink)',
        muted: 'var(--color-muted)',
        border: 'var(--color-border)',
        primary: 'var(--color-primary)',
        info: 'var(--color-info)',
        success: 'var(--color-success)',
        warn: 'var(--color-warn)',
        danger: 'var(--color-danger)'
      },
      borderRadius: {
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)'
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Manrope', 'Inter', 'system-ui'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace']
      }
    }
  }
}
```

---

## 11) Примеры применения (соглашения)

* **Primary button:** `class="bg-primary text-[var(--color-primary-ink)] rounded-xs px-4 py-2 shadow-sm hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[--focus-ring] focus-visible:ring-offset-2"`
* **Card:** `class="bg-elev border border-border rounded-sm shadow-sm p-4"`
* **Muted text:** `class="text-muted"`
* **Danger chip:** фон `#FF7676` @12%, текст `#FF7676`.

---

## 12) Иконки и иллюстрации

* Иконки: *Lucide* / *Remix*; размер 16/20/24; цвет = `currentColor` (наследуем текстовый).
* Иллюстрации — минималистичные, линейные, без «плоского мультяшного» стиля.

---

## 13) Доступность

* Контраст: заголовки/текст ≥ 4.5:1 (проверять при обоих темах).
* Фокус всегда видим; не убирать outline без замены.
* Размер кликабельных зон ≥ 40×40.
* Язык `lang="ru"` по умолчанию; поддержка английского позднее.

---

## 14) Что пойдёт в следующую версию

* Токены для «режима чтения» (узкая колонка, ещё выше контраст).
* Специфика редактирования LaTeX/формул.
* Паттерны для коллаборативных правок/версий.

---

### TL;DR

Спокойная академичная тёмная тема с индиго‑акцентом, строгая типографика Inter/Manrope, холодные нейтрали, мягкие тени, акцент на читабельности и фокусе. Всё завязано на CSS‑переменных и Tailwind токенах — легко настраивать и масштабировать.
