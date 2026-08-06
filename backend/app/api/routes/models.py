from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, Pagination
from app.api.schemas.settings import AvailableModelResponse, ModelsListResponse

router = APIRouter(tags=["models"])


@router.get("/models", response_model=ModelsListResponse)
async def list_models(
    request: Request,
    user: CurrentUser,
    page: Pagination,
) -> ModelsListResponse:
    models = request.app.state.agent_config.available_models
    items = models[page.offset : page.offset + page.limit]
    return ModelsListResponse(
        items=[
            AvailableModelResponse(name=m.name, display_name=m.display_name)
            for m in items
        ],
        total=len(models),
        limit=page.limit,
        offset=page.offset,
    )
