from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.schemas.settings import AvailableModelResponse, ModelsListResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsListResponse)
async def list_models(request: Request) -> ModelsListResponse:
    agent_config = request.app.state.agent_config
    return ModelsListResponse(
        items=[
            AvailableModelResponse(name=m.name, display_name=m.display_name)
            for m in agent_config.available_models
        ]
    )
