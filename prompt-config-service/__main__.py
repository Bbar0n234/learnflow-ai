"""Entry point for running the service as a module."""

import uvicorn

from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.service_host,
        port=settings.service_port
    )