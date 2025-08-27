"""FastAPI application for Artifacts Service."""

import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, status, Path as PathParam, Query
from fastapi.responses import PlainTextResponse, JSONResponse, FileResponse, Response
from contextlib import asynccontextmanager

from .storage import ArtifactsStorage
from .models import (
    HealthResponse,
    ThreadsListResponse,
    ThreadDetailResponse,
    SessionFilesResponse,
    FileContent,
    FileOperationResponse,
    ErrorResponse,
    ExportFormat,
    PackageType,
    ExportSettings,
    SessionSummary,
    ExportRequest,
)
from .exceptions import ArtifactsServiceException, map_to_http_exception
from .settings import settings
from .services.export import MarkdownExporter, PDFExporter, ZIPExporter

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console
        logging.FileHandler(log_dir / "artifacts.log", encoding="utf-8")  # File
    ]
)

# Global storage instance
storage = ArtifactsStorage()

# Logger instance
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    # Ensure data directory exists
    storage.base_path.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown - cleanup if needed


# FastAPI application
app = FastAPI(
    title="Artifacts Service",
    description="File storage system for LearnFlow AI artifacts",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(ArtifactsServiceException)
async def service_exception_handler(request, exc: ArtifactsServiceException):
    """Handle service exceptions."""
    http_exc = map_to_http_exception(exc)
    return JSONResponse(
        status_code=http_exc.status_code,
        content=ErrorResponse(error=str(exc)).model_dump(),
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        # Check if storage is accessible
        storage.base_path.exists()
        return HealthResponse(status="ok")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable: {str(e)}",
        )


@app.get("/threads", response_model=ThreadsListResponse)
async def get_threads():
    """Get list of all threads."""
    try:
        threads = storage.get_threads()
        return ThreadsListResponse(threads=threads)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get threads: {str(e)}",
        )


@app.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(thread_id: str = PathParam(description="Thread identifier")):
    """Get information about a specific thread."""
    try:
        thread_info = storage.get_thread_info(thread_id)
        return ThreadDetailResponse(
            thread_id=thread_info.thread_id,
            sessions=thread_info.sessions,
            created=thread_info.created,
            last_activity=thread_info.last_activity,
            sessions_count=thread_info.sessions_count,
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.get(
    "/threads/{thread_id}/sessions/{session_id}", response_model=SessionFilesResponse
)
async def get_session_files(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
):
    """Get list of files in a session."""
    try:
        files = storage.get_session_files(thread_id, session_id)
        return SessionFilesResponse(
            thread_id=thread_id, session_id=session_id, files=files
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.get("/threads/{thread_id}/sessions/{session_id}/{file_path:path}")
async def get_file(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session"),
):
    """Get file content."""
    try:
        content = storage.read_file(thread_id, session_id, file_path)

        # Determine response type based on file extension
        if file_path.endswith(".json"):
            return JSONResponse(content=content)
        else:
            return PlainTextResponse(content=content, media_type="text/plain")

    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.post(
    "/threads/{thread_id}/sessions/{session_id}/{file_path:path}",
    response_model=FileOperationResponse,
)
async def create_or_update_file(
    file_content: FileContent,
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session"),
):
    """Create or update a file in a session."""
    try:
        # Check if file already exists
        file_exists = False
        try:
            storage.read_file(thread_id, session_id, file_path)
            file_exists = True
        except Exception as e:
            logger.debug(f"File {file_path} not found, will create new: {e}")

        # Write the file
        storage.write_file(
            thread_id=thread_id,
            session_id=session_id,
            path=file_path,
            content=file_content.content,
            content_type=file_content.content_type,
        )

        if file_exists:
            return FileOperationResponse(message="File updated", path=file_path)
        else:
            return FileOperationResponse(message="File created", path=file_path)

    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete(
    "/threads/{thread_id}/sessions/{session_id}/{file_path:path}",
    response_model=FileOperationResponse,
)
async def delete_file(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session"),
):
    """Delete a file from a session."""
    try:
        storage.delete_file(thread_id, session_id, file_path)
        return FileOperationResponse(message="File deleted", path=file_path)
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete(
    "/threads/{thread_id}/sessions/{session_id}", response_model=FileOperationResponse
)
async def delete_session(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
):
    """Delete an entire session with all files."""
    try:
        storage.delete_session(thread_id, session_id)
        return FileOperationResponse(message="Session deleted")
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete("/threads/{thread_id}", response_model=FileOperationResponse)
async def delete_thread(thread_id: str = PathParam(description="Thread identifier")):
    """Delete an entire thread with all sessions."""
    try:
        storage.delete_thread(thread_id)
        return FileOperationResponse(message="Thread deleted")
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


# Export API Endpoints

# Store user settings in memory (in production, use a database)
user_settings = {}


@app.get("/threads/{thread_id}/sessions/{session_id}/export/single")
async def export_single_document(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    document_name: str = Query(description="Document name to export"),
    format: ExportFormat = Query(ExportFormat.MARKDOWN, description="Export format"),
):
    """Export a single document."""
    try:
        # Select exporter based on format
        if format == ExportFormat.PDF:
            exporter = PDFExporter(storage.base_path)
        else:
            exporter = MarkdownExporter(storage.base_path)
        
        # Export document
        content = await exporter.export_single_document(
            thread_id, session_id, document_name, format
        )
        
        # Determine file extension and mime type
        if format == ExportFormat.PDF:
            ext = "pdf"
            media_type = "application/pdf"
        else:
            ext = "md"
            media_type = "text/markdown"
        
        # Format filename
        filename = exporter.format_filename(document_name, session_id, ext)
        
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@app.get("/threads/{thread_id}/sessions/{session_id}/export/package")
async def export_package(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    package_type: PackageType = Query(PackageType.FINAL, description="Package type"),
    format: ExportFormat = Query(ExportFormat.MARKDOWN, description="Export format"),
):
    """Export a package of documents as ZIP archive."""
    try:
        # Use ZIP exporter
        zip_exporter = ZIPExporter(storage.base_path)
        
        # Export package
        content = await zip_exporter.export_session_archive(
            thread_id, session_id, package_type, format
        )
        
        # Format filename
        filename = f"session_{session_id}_export.zip"
        
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@app.get("/users/{user_id}/sessions/recent", response_model=List[SessionSummary])
async def get_recent_sessions(
    user_id: str = PathParam(description="User identifier"),
    limit: int = Query(5, max=5, description="Maximum number of sessions"),
):
    """Get list of recent sessions for export."""
    try:
        # Find user's threads
        # In production, this would query a database for user-thread mapping
        # For now, we'll return all recent sessions
        all_threads = storage.get_threads()
        
        sessions_list = []
        for thread in all_threads[:limit]:  # Limit threads for performance
            for session in thread.sessions[:limit]:
                # Create session summary
                summary = SessionSummary(
                    thread_id=thread.thread_id,
                    session_id=session.session_id,
                    exam_question=session.exam_question,
                    question_preview=session.exam_question[:30] + "..." 
                        if len(session.exam_question) > 30 else session.exam_question,
                    display_name=f"{session.exam_question[:30]}... - {session.created.strftime('%d.%m.%Y')}",
                    created_at=session.created,
                    has_synthesized=False,  # Check if synthesized_material.md exists
                    has_questions=False,     # Check if gap_questions.md exists
                    answers_count=0          # Count answer files
                )
                sessions_list.append(summary)
                
                if len(sessions_list) >= limit:
                    break
            
            if len(sessions_list) >= limit:
                break
        
        return sessions_list
    except Exception as e:
        logger.error(f"Failed to get recent sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recent sessions: {str(e)}"
        )


@app.get("/users/{user_id}/export-settings", response_model=ExportSettings)
async def get_export_settings(
    user_id: str = PathParam(description="User identifier")
):
    """Get user export settings."""
    # Return existing settings or create default
    if user_id not in user_settings:
        user_settings[user_id] = ExportSettings(user_id=user_id)
    
    return user_settings[user_id]


@app.put("/users/{user_id}/export-settings", response_model=ExportSettings)
async def update_export_settings(
    user_id: str = PathParam(description="User identifier"),
    settings: ExportSettings = ...,
):
    """Update user export settings."""
    settings.user_id = user_id
    settings.modified = datetime.now()
    user_settings[user_id] = settings
    return settings


def main():
    """Main entry point for running the server."""
    import uvicorn

    uvicorn.run(
        "artifacts-service.main:app",
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
