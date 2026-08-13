from app.agent.tools.execution import make_execution_tools
from app.agent.tools.files import make_file_tools
from app.agent.tools.image_generation import make_generate_image_tool
from app.agent.tools.knowledge_sphere import (
    create_section,
    delete_section,
    get_section,
    update_section,
)
from app.agent.tools.skill_context import make_skill_context_tools
from app.agent.tools.skills import (
    make_load_skill_tool,
    scan_skill_names,
    scan_skills_index,
)
from app.agent.tools.subagents import (
    build_run_subagent_description,
    make_run_subagent_tool,
)
from app.agent.tools.user_memory import delete_user_memory, save_user_memory

ks_tools = [get_section, create_section, update_section, delete_section]
user_memory_tools = [save_user_memory, delete_user_memory]

__all__ = [
    "ks_tools",
    "user_memory_tools",
    "build_run_subagent_description",
    "make_execution_tools",
    "make_file_tools",
    "make_generate_image_tool",
    "make_load_skill_tool",
    "make_run_subagent_tool",
    "make_skill_context_tools",
    "scan_skill_names",
    "scan_skills_index",
]

# `registry` is imported lazily by consumers (`app.main`,
# `scripts/generate_tool_names_fixture.py`, the T1.8 drift-gate test) via
# `app.agent.tools.registry` directly rather than re-exported here: it
# imports `ks_tools`/`user_memory_tools` back from this module, and adding it
# to `__all__` would buy no ergonomics beyond one extra import line.
