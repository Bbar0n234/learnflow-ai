"""Смоук-скрипт для feat-003 (model-selection): боевые вызовы OpenRouter.

Платный скрипт — каждый прогон делает реальные chat-completions вызовы к
OpenRouter (небольшой промпт на модель), деньги со счёта проекта списываются.
НЕ входит в `make test`/CI, запускается вручную архитектором/оркестратором.

Проверяет по каждой модели утверждённого состава feat-003, что:
  - модель отвечает на короткий запрос;
  - при заданном reasoning-конфиге (effort/exclude) она реально возвращает
    рассуждения и в каком виде — полные (`reasoning.text`), суммаризованные
    (`reasoning.summary`) или не возвращает вовсе;
  - usage корректно репортит `completion_tokens_details.reasoning_tokens`.

Особый интерес архитектора: отдаёт ли guard-модель `google/gemini-3.5-flash-lite`
рассуждения при `effort: minimal` (прецедент: GLM-4.7 Flash — отдавала,
Gemini 3.1 Flash Lite — не отдавала). Строка guard в таблице выделена явно.

Запуск (из корня worktree):
    uv run --package learnflow-backend python \
        doc/tasks/iterations/dogfooding/feat-003-model-selection/model_smoke.py

или просто `python <путь>`, если в окружении уже есть httpx.

Ключ и base URL берутся из `.env` в корне worktree (`LLM_API_KEY`,
`LLM_BASE_URL`), а если файла/переменных там нет — из окружения процесса.
Без ключа скрипт печатает понятную ошибку и завершается с exit code 1
(до попытки сделать хоть один сетевой вызов).
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

REASONING_MEDIUM = {"effort": "medium", "exclude": False}
REASONING_MINIMAL = {"effort": "minimal", "exclude": False}

PROMPT = "In one short sentence, what is the capital of France?"
MAX_TOKENS = 2000
REQUEST_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class ModelCase:
    slug: str
    role: str  # "whitelist" | "summarization/subagents" | "guard"
    reasoning: dict[str, Any]
    highlight: bool = False


# Утверждённый состав feat-003 (design-brief § Утверждённый состав).
MODEL_CASES: list[ModelCase] = [
    ModelCase("z-ai/glm-5.2", "whitelist (main llm)", REASONING_MEDIUM),
    ModelCase("google/gemini-3.6-flash", "whitelist", REASONING_MEDIUM),
    ModelCase("deepseek/deepseek-v4-pro", "whitelist", REASONING_MEDIUM),
    ModelCase("meta/muse-spark-1.1", "whitelist", REASONING_MEDIUM),
    ModelCase("qwen/qwen3.7-max", "whitelist", REASONING_MEDIUM),
    ModelCase(
        "deepseek/deepseek-v4-flash",
        "summarization/subagents",
        REASONING_MEDIUM,
    ),
    ModelCase(
        "google/gemini-3.5-flash-lite",
        "guard (llm_classifier)",
        REASONING_MINIMAL,
        highlight=True,
    ),
]


@dataclass
class SmokeResult:
    case: ModelCase
    ok: bool = False
    answer_preview: str = ""
    reasoning_shape: str = "нет"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: float = 0.0
    error: str | None = None
    raw_reasoning_details: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def _parse_env_file(path: Path) -> dict[str, str]:
    """Минимальный парсер .env: KEY=VALUE построчно, без интерполяции."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def resolve_credentials() -> tuple[str, str]:
    """Возвращает (api_key, base_url): сначала .env worktree, иначе env процесса."""
    env_path = Path(__file__).resolve().parents[5] / ".env"
    dotenv_values = _parse_env_file(env_path)

    api_key = dotenv_values.get("LLM_API_KEY") or os.environ.get("LLM_API_KEY", "")
    base_url = (
        dotenv_values.get("LLM_BASE_URL")
        or os.environ.get("LLM_BASE_URL")
        or DEFAULT_BASE_URL
    )

    if not api_key:
        print(
            "ОШИБКА: LLM_API_KEY не найден ни в .env "
            f"({env_path}), ни в переменных окружения процесса.\n"
            "Задайте LLM_API_KEY (ключ OpenRouter) перед запуском смоук-скрипта.",
            file=sys.stderr,
        )
        sys.exit(1)

    return api_key, base_url


# ---------------------------------------------------------------------------
# Call + classification
# ---------------------------------------------------------------------------


def _classify_reasoning(message: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Классифицирует форму рассуждений: полные | суммаризованные | нет."""
    details = message.get("reasoning_details") or []
    types_seen = {d.get("type") for d in details if isinstance(d, dict)}

    if "reasoning.text" in types_seen:
        return "полные", details
    if "reasoning.summary" in types_seen:
        return "суммаризованные", details
    if "reasoning.encrypted" in types_seen:
        # Зашифрованные детали не дают текст, но сигнализируют, что
        # рассуждения были — считаем как "нет" для целей юзабельности вывода,
        # но помечаем отдельно, чтобы не потерять сигнал.
        return "нет (зашифровано)", details

    if message.get("reasoning"):
        return "полные", details

    return "нет", details


def call_model(
    client: httpx.Client,
    base_url: str,
    case: ModelCase,
) -> SmokeResult:
    result = SmokeResult(case=case)
    # OpenRouter принимает reasoning-конфиг как top-level поле запроса
    # (совпадает с содержимым agent.yaml/security.yaml extra_body.reasoning).
    payload = {
        "model": case.slug,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS,
        "reasoning": case.reasoning,
    }

    start = time.monotonic()
    try:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json=payload,
            timeout=REQUEST_TIMEOUT_S,
        )
        result.latency_ms = (time.monotonic() - start) * 1000
        response.raise_for_status()
        data = response.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""

        result.ok = bool(content)
        result.answer_preview = content[:60].replace("\n", " ")
        result.reasoning_shape, result.raw_reasoning_details = _classify_reasoning(message)

        usage = data.get("usage") or {}
        result.prompt_tokens = usage.get("prompt_tokens")
        result.completion_tokens = usage.get("completion_tokens")
        completion_details = usage.get("completion_tokens_details") or {}
        result.reasoning_tokens = completion_details.get("reasoning_tokens")

        if not result.ok:
            result.error = f"пустой content (finish_reason={choice.get('finish_reason')})"

    except httpx.HTTPStatusError as exc:
        result.latency_ms = (time.monotonic() - start) * 1000
        body_preview = exc.response.text[:200] if exc.response is not None else ""
        result.error = f"HTTP {exc.response.status_code if exc.response else '?'}: {body_preview}"
    except httpx.HTTPError as exc:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.error = f"сетевая ошибка: {exc!r}"
    except (KeyError, ValueError, TypeError) as exc:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.error = f"неожиданный формат ответа: {exc!r}"

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt_tokens(value: int | None) -> str:
    return str(value) if value is not None else "-"


def print_report(results: list[SmokeResult]) -> None:
    header = (
        f"{'модель':<32} {'роль':<26} {'ответ':<6} {'рассуждения':<22} "
        f"{'prompt':>7} {'compl':>7} {'reason.tok':>10} {'latency,ms':>10}"
    )
    print(header)
    print("-" * len(header))

    for r in results:
        marker = ">> " if r.case.highlight else "   "
        answer_flag = "да" if r.ok else "НЕТ"
        line = (
            f"{marker}{r.case.slug:<29} {r.case.role:<26} {answer_flag:<6} "
            f"{r.reasoning_shape:<22} {_fmt_tokens(r.prompt_tokens):>7} "
            f"{_fmt_tokens(r.completion_tokens):>7} "
            f"{_fmt_tokens(r.reasoning_tokens):>10} {r.latency_ms:>10.0f}"
        )
        print(line)
        if r.error:
            print(f"      ошибка: {r.error}")
        elif r.ok:
            print(f'      ответ: "{r.answer_preview}"')

    print()
    guard_results = [r for r in results if r.case.highlight]
    for guard in guard_results:
        print(
            f"Особый интерес архитектора — guard {guard.case.slug} "
            f"(effort=minimal): рассуждения = {guard.reasoning_shape}."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    api_key, base_url = resolve_credentials()

    print(f"OpenRouter base_url={base_url}")
    print(f"Моделей к прогону: {len(MODEL_CASES)}\n")

    results: list[SmokeResult] = []
    with httpx.Client(
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    ) as client:
        for case in MODEL_CASES:
            print(f"-> {case.slug} ({case.role}) ...")
            result = call_model(client, base_url, case)
            results.append(result)

    print()
    print_report(results)

    failures = [r for r in results if not r.ok]
    if failures:
        print(f"\n{len(failures)} из {len(results)} моделей не вернули ответ.")


if __name__ == "__main__":
    main()
