from jinja2 import Template

SYSTEM_MESSAGE_TEMPLATE = Template("""\
{{ based_prompt }}

{% if custom_instructions %}
<custom_instructions>
{{ custom_instructions }}
</custom_instructions>

{% endif %}
{% if user_memory_index %}
<user_memory>
{{ user_memory_index }}
</user_memory>

{% endif %}
<knowledge_sphere>
{{ ks_index }}
</knowledge_sphere>

{% if skills_index %}
<available_skills>
{{ skills_index }}
</available_skills>
{% endif %}
""")


def build_system_message(
    based_prompt: str,
    ks_index: str,
    skills_index: str = "",
    custom_instructions: str = "",
    user_memory_index: str = "",
) -> str:
    return SYSTEM_MESSAGE_TEMPLATE.render(
        based_prompt=based_prompt,
        ks_index=ks_index,
        skills_index=skills_index,
        custom_instructions=custom_instructions,
        user_memory_index=user_memory_index,
    )
