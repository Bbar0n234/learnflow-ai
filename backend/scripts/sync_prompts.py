"""Sync prompts from Langfuse to local files.

Prompt names are qualified with label: "system--development", "system--production".

Usage: uv run python backend/scripts/sync_prompts.py --label production
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from langfuse import Langfuse

CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"
PROMPTS_DIR = CONFIGS_DIR / "prompts"
AGENT_YAML = CONFIGS_DIR / "agent.yaml"
SECURITY_YAML = CONFIGS_DIR / "security.yaml"

PROMPT_NAMES = ["system", "summarization", "security-classifier"]


def sync_to_files(label: str) -> None:
    langfuse = Langfuse()
    if not langfuse.auth_check():
        print("Langfuse auth failed")
        return

    for name in PROMPT_NAMES:
        qualified = f"{name}--{label}"
        try:
            prompt = langfuse.get_prompt(qualified)
        except Exception as e:
            print(f"Skipping {qualified}: {e}")
            continue

        text = prompt.compile()
        config = prompt.config

        file_path = PROMPTS_DIR / f"{name}.txt"
        file_path.write_text(text, encoding="utf-8")
        print(f"Written: {file_path}")

        if config:
            _update_yaml_config(name, config)

    langfuse.shutdown()


def _update_yaml_config(prompt_name: str, config: dict) -> None:
    if prompt_name == "security-classifier":
        _update_security_yaml(config)
    else:
        _update_agent_yaml(prompt_name, config)


def _update_agent_yaml(prompt_name: str, config: dict) -> None:
    with open(AGENT_YAML) as f:
        data = yaml.safe_load(f) or {}

    if prompt_name == "system" and "model" in config:
        data.setdefault("llm", {})["model"] = config["model"]
        if "extra_body" in config:
            data["llm"]["extra_body"] = config["extra_body"]
    elif prompt_name == "summarization" and "model" in config:
        data.setdefault("summarization", {})["model"] = config["model"]
        if "max_tokens" in config:
            data["summarization"]["max_summary_tokens"] = config["max_tokens"]
        if "extra_body" in config:
            data["summarization"]["extra_body"] = config["extra_body"]

    with open(AGENT_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"Updated agent.yaml for {prompt_name}")


def _update_security_yaml(config: dict) -> None:
    with open(SECURITY_YAML) as f:
        data = yaml.safe_load(f) or {}

    classifier = data.setdefault("llm_classifier", {})
    if "model" in config:
        classifier["model"] = config["model"]
    if "extra_body" in config:
        classifier["extra_body"] = config["extra_body"]

    with open(SECURITY_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print("Updated security.yaml for security-classifier")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="production")
    args = parser.parse_args()
    sync_to_files(args.label)
