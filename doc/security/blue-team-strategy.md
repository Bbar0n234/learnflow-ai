# Blue Team Strategy — LearnFlowAI

Стратегия защиты проекта LearnFlowAI в рамках дисциплины "Защита от нейронных сетей".

Дата создания: 2026-02-23

---

## Контекст дисциплины

Red Team vs Blue Team. Группа делится на две команды:
- **Blue Team** — выбирает приложение и вектор защиты, строит защиту
- **Red Team** — атакует после того, как Blue определит scope

Направление: **LLM** (не CV).

Blue задаёт темп — от неё зависит, когда Red сможет начать работу.

---

## Проект для защиты

**LearnFlowAI** — AI-агент для подготовки материалов: доклады, статьи, курсы, лекции и другие форматы.

Стек: FastAPI + LangGraph + React + PostgreSQL.

Почему подходит:
- Реальное LLM-приложение с реальными векторами атак
- Защита, реализованная для курса, остаётся в продакшене
- Open-source — Red Team имеет доступ к исходному коду (принцип Кирхгоффа)

---

## Принцип Кирхгоффа

Проект open-source. Репозиторий доступен Red Team. Знание алгоритма (архитектуры, кода) не должно подрывать защищённость. Безопасность системы строится не на сокрытии, а на качестве реализации защитных механизмов.

---

## Вектора защиты

### V1: Direct Prompt Injection + Jailbreak

**Угроза:** Пользователь через текстовый ввод (Web UI) пытается обойти system prompt, изменить поведение агента или извлечь конфиденциальную информацию.

**Стратегия защиты:**

| Слой | Механизм | Описание |
|------|----------|----------|
| 1 | Robust System Prompt | Чёткие инструкции, явные запреты, reinforcement boundaries |
| 2 | Input Classification | Классификатор входящих сообщений (detect injection attempts) |
| 3 | Output Filtering | Проверка ответов агента перед отправкой пользователю |
| 4 | Prompt Hardening | Techniques: delimiter separation, sandwich defense, instruction hierarchy |
| 5 | Monitoring & Logging | Langfuse — трейсинг всех взаимодействий для анализа |

**Планируемые техники:**
- Instruction hierarchy: system > user (явно в промпте)
- Delimiter-based isolation: чёткое разделение system/user/context
- Canary tokens: маркеры утечки system prompt
- Behavior boundaries: hardcoded limits на что агент может/не может
- Multi-layer validation: input → agent → output pipeline

### V2: Indirect Prompt Injection + Memory Poisoning

**Угроза:** Вредоносные инструкции в загружаемых файлах + отравление Knowledge Sphere (персистентной памяти).

> **Примечание:** File upload — планируемый компонент. Детали реализации будут уточнены.

**Стратегия защиты:**

| Слой | Механизм | Описание |
|------|----------|----------|
| 1 | File Sanitization | Очистка файлов: удаление metadata, hidden text, zero-width chars |
| 2 | Content Isolation | Файловый контент обрабатывается с пометкой "untrusted data" |
| 3 | KS Validation | Проверка данных перед записью в Knowledge Sphere |
| 4 | KS Integrity Checks | Периодическая проверка целостности шара знаний |
| 5 | Rollback Capability | Возможность откатить Knowledge Sphere к предыдущему состоянию |

**Планируемые техники:**
- Файловый контент оборачивается в delimiter'ы: `[UNTRUSTED CONTENT START]...[END]`
- System prompt явно инструктирует не выполнять инструкции из пользовательского контента
- Валидация данных перед записью в Knowledge Sphere (проверка на подозрительный контент)
- Версионирование Knowledge Sphere (возможность diff и rollback)

### V3: Infrastructure Abuse

**Угроза:** Rate limit bypass, DoS, resource exhaustion через API.

**Стратегия защиты:**

| Слой | Механизм | Описание |
|------|----------|----------|
| 1 | Rate Limiting | Лимиты на requests/min, tokens/min per user |
| 2 | Input Validation | Max message length, max file size, allowed file types |
| 3 | Request Throttling | Backpressure при высокой нагрузке |
| 4 | Resource Quotas | Лимиты на проекты, чаты, storage per user |
| 5 | Monitoring | Alerting при аномальной активности |

**Планируемые техники:**
- FastAPI middleware для rate limiting (sliding window)
- Pydantic models для strict input validation
- Max message size: configurable
- Max file size: configurable
- Allowed file types: whitelist (PDF, DOCX, PPTX, MD, TXT)
- Concurrent request limit per session

---

## Разделение ролей в команде

> TODO: Будет определено после формирования команды.

---

## Задачи команды

> TODO: Будут сформулированы и распределены после определения состава и ролей.

---

## Таймлайн

> TODO: Будет определён с учётом расписания дисциплины и прогресса по MVP.

---

## Связанные документы

- [Threat Model](threat-model.md) — модель угроз
- [Red Team Brief](red-team-brief.md) — брифинг для Red Team
