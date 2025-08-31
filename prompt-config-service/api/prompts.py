"""API endpoints for prompt generation operations."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.prompt import GeneratePromptRequest, GeneratePromptResponse
from services.prompt_service import PromptService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["prompts"])


@router.post("/generate-prompt", response_model=GeneratePromptResponse)
async def generate_prompt(
    request: GeneratePromptRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate prompt with dynamic placeholder resolution.
    
    Process:
    1. Load template from YAML by node_name
    2. Extract placeholders from template 
    3. Use context values where available (priority)
    4. Fetch missing placeholders from user settings
    5. Log warnings for unavailable placeholders
    6. Render final prompt
    """
    service = PromptService(db)
    
    try:
        response = await service.generate_prompt(
            user_id=request.user_id,
            node_name=request.node_name,
            context=request.context
        )
        return response
    except ValueError as e:
        # Template not found, rendering failed, etc.
        logger.error(f"Bad request for {request.node_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Database errors, unexpected issues
        logger.error(f"Failed to generate prompt for {request.node_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt generation failed: {str(e)}"
        )