"""Entry point for running the service as a module."""

import uvicorn

from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "prompt_config_service.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True if settings.log_level == "DEBUG" else False
    )