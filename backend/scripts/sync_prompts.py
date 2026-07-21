"""Sync prompts from Langfuse to local files.

Prompt names are qualified with label: "system--development", "system--production".

The set of prompts and their config write-back targets come from
``configs/prompts.yaml`` (the same registry the seed direction in
``app.main._seed_prompts`` iterates) — adding a subagent is a config-only
change, this script needs no edit.

Usage: make sync-prompts (runs from backend/ so the ``app`` package resolves)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from app.agent.config import PromptEntry, load_prompts_registry
from langfuse import Langfuse

CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"
PROMPTS_DIR = CONFIGS_DIR / "prompts"
PROMPTS_YAML = CONFIGS_DIR / "prompts.yaml"

# Root of a registry ``source`` path -> the yaml file that section lives in.
SOURCE_FILES = {
    "agent": CONFIGS_DIR / "agent.yaml",
    "security": CONFIGS_DIR / "security.yaml",
}


def sync_to_files(label: str) -> None:
    registry = load_prompts_registry(PROMPTS_YAML)
    langfuse = Langfuse()
    if not langfuse.auth_check():
        print("Langfuse auth failed")
        return

    # Several prompts may feed the same config section (all subagent-* map
    # onto agent.subagents.llm), so configs are collected per source and
    # written back once, after checking they agree.
    pending: dict[str, tuple[PromptEntry, list[tuple[str, dict[str, Any]]]]] = {}

    for name, entry in registry.prompts.items():
        qualified = f"{name}--{label}"
        try:
            prompt = langfuse.get_prompt(qualified)
        except Exception as e:
            print(f"Skipping {qualified}: {e}")
            continue

        text = prompt.compile()

        file_path = PROMPTS_DIR / f"{name}.txt"
        file_path.write_text(text, encoding="utf-8")
        print(f"Written: {file_path}")

        if prompt.config:
            _, named_configs = pending.setdefault(entry.source, (entry, []))
            named_configs.append((name, prompt.config))

    for source, (entry, named_configs) in pending.items():
        _write_back_config(source, entry, named_configs)

    langfuse.shutdown()


def _write_back_config(
    source: str,
    entry: PromptEntry,
    named_configs: list[tuple[str, dict[str, Any]]],
) -> None:
    """Write Langfuse prompt config back into the yaml section ``source`` names.

    Skips (with a message, never a partial write) when the source path is
    unknown, when prompts sharing the section disagree, or when nothing
    would change — ``yaml.dump`` loses comments and formatting, so the file
    is only rewritten for an actual update.
    """
    root, _, section_path = source.partition(".")
    target_file = SOURCE_FILES.get(root)
    if target_file is None or not section_path:
        print(f"Skipping config write-back for {source}: unknown source path")
        return

    # Compare only the mapped keys: unrelated config entries on a prompt must
    # not block the write-back, but diverging mapped values would make the
    # result depend on iteration order — refuse instead of last-wins.
    projections = [
        (
            name,
            {
                yaml_key: config[config_key]
                for config_key, yaml_key in entry.keys.items()
                if config_key in config
            },
        )
        for name, config in named_configs
    ]
    reference_name, updates = projections[0]
    diverging = [name for name, projection in projections[1:] if projection != updates]
    if diverging:
        print(
            f"Skipping config write-back for {source}: configs diverge between "
            f"{reference_name} and {', '.join(diverging)} — align them in Langfuse"
        )
        return
    if not updates:
        return

    with open(target_file) as f:
        data = yaml.safe_load(f) or {}

    section = data
    for part in section_path.split("."):
        section = section.setdefault(part, {})

    if all(section.get(key) == value for key, value in updates.items()):
        return

    section.update(updates)
    with open(target_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    print(f"Updated {target_file.name}: {section_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="production")
    args = parser.parse_args()
    sync_to_files(args.label)
