"""Service for prompt generation operations."""

import logging
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from schemas.prompt import GeneratePromptRequest, GeneratePromptResponse
from utils.jinja_renderer import extract_placeholders, render_template
from utils.template_loader import load_template
from services.user_service import UserService

logger = logging.getLogger(__name__)


class PromptService:
    """Service for generating prompts with dynamic placeholder resolution."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service = UserService(db)
    
    async def generate_prompt(
        self, user_id: int, node_name: str, context: Dict
    ) -> GeneratePromptResponse:
        """
        Generate prompt with dynamic placeholder resolution:
        1. Load template from YAML by node_name
        2. Extract all placeholders from template through Jinja2 meta
        3. Check which placeholders are in context (they have priority)
        4. Query database only for missing placeholders not in context
        5. Log warning for placeholders not found in either context or database
        6. Render final prompt
        """
        
        # 1. Load template
        try:
            template_str = await load_template(node_name)
        except (ValueError, FileNotFoundError) as e:
            logger.error(f"Template loading failed for node {node_name}: {e}")
            raise ValueError(f"Template not found for node: {node_name}") from e
        
        # 2. Extract all placeholders from template
        all_placeholders = extract_placeholders(template_str)
        logger.debug(f"Found placeholders in template for {node_name}: {all_placeholders}")
        
        # 3. Determine which placeholders are already in context
        context_placeholders = set(all_placeholders) & set(context.keys())
        missing_placeholders = set(all_placeholders) - set(context.keys())
        
        logger.debug(f"Placeholders from context: {context_placeholders}")
        logger.debug(f"Need to fetch from DB: {missing_placeholders}")
        
        # 4. Query database only for missing placeholders
        db_values = {}
        if missing_placeholders:
            try:
                db_values = await self.user_service.get_user_placeholder_values(
                    user_id, list(missing_placeholders)
                )
            except Exception as e:
                logger.error(f"Failed to get user placeholder values: {e}")
                # Continue with empty db_values - will be logged as missing
        
        # 5. Check that all placeholders are found
        final_values = {**db_values, **context}  # context has priority
        not_found = set(all_placeholders) - set(final_values.keys())
        
        if not_found:
            logger.warning(
                f"Missing placeholders for user {user_id}, node {node_name}: {not_found}. "
                f"These will be rendered as empty strings."
            )
            # Add empty strings for missing placeholders to prevent Jinja2 errors
            for placeholder in not_found:
                final_values[placeholder] = ""
        
        # 6. Render template
        try:
            prompt = await render_template(template_str, final_values)
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            raise ValueError(f"Failed to render prompt: {e}") from e
        
        logger.info(
            f"Successfully generated prompt for user {user_id}, node {node_name}. "
            f"Used {len(final_values)} placeholders."
        )
        
        return GeneratePromptResponse(
            prompt=prompt,
            used_placeholders=final_values
        )