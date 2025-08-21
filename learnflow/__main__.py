"""
Entrypoint for running LearnFlow AI as a module with `python -m learnflow`.
"""

if __name__ == "__main__":
    from .config.settings import get_settings
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "learnflow.api.main:app",
        host=settings.host,
        port=settings.port,
    )
