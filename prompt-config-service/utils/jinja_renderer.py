"""Jinja2 template rendering utilities."""

import logging
from typing import Any, Dict, List

from jinja2 import Environment, meta

logger = logging.getLogger(__name__)

# Global Jinja2 environment
_jinja_env = Environment(
    autoescape=True,  # Security: escape variables by default
    trim_blocks=True,
    lstrip_blocks=True
)


def extract_placeholders(template_str: str) -> List[str]:
    """Extract all placeholder variables from Jinja2 template."""
    try:
        parsed = _jinja_env.parse(template_str)
        placeholders = list(meta.find_undeclared_variables(parsed))
        return placeholders
    except Exception as e:
        logger.error(f"Failed to extract placeholders from template: {e}")
        return []


async def render_template(template_str: str, values: Dict[str, Any]) -> str:
    """Render Jinja2 template with provided values."""
    try:
        template = _jinja_env.from_string(template_str)
        return template.render(**values)
    except Exception as e:
        logger.error(f"Failed to render template: {e}")
        logger.error(f"Template: {template_str[:100]}...")
        logger.error(f"Values: {values}")
        raise ValueError(f"Template rendering failed: {e}") from e