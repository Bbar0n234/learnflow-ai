"""FastAPI application for Artifacts Service."""

import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, status, Path as PathParam, Query, Depends
from fastapi.responses import PlainTextResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel

from storage import ArtifactsStorage
from auth import auth_service, require_auth, verify_resource_owner
from auth_models_api import AuthCodeRequest, AuthTokenResponse
from models import (
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
from exceptions import ArtifactsServiceException, map_to_http_exception
from settings import settings
from services.export import MarkdownExporter, PDFExporter, ZIPExporter

# Create logs directory if it doesn't exist
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
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
    # Connect auth service
    await auth_service.connect()
    yield
    # Shutdown - cleanup if needed
    await auth_service.disconnect()


# FastAPI application
app = FastAPI(
    title="Artifacts Service",
    description="File storage system for LearnFlow AI artifacts",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for Web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Vite preview
        "http://localhost:3000",  # Alternative dev port
        "http://127.0.0.1:5173",  # IP access for Telegram bot links
        "http://127.0.0.1:5174",  # IP access preview
        "http://127.0.0.1:3000",  # IP access alternative
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.post("/auth/verify", response_model=AuthTokenResponse)
async def verify_auth_code(request: AuthCodeRequest):
    """Verify auth code and return JWT token."""
    if not auth_service.pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service not available"
        )
    
    user_id = await auth_service.verify_auth_code(request.username, request.code)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired auth code"
        )
    
    # Create JWT token
    token = auth_service.create_jwt_token(user_id, request.username)
    
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiration_minutes * 60
    )


@app.get("/threads", response_model=ThreadsListResponse, dependencies=[Depends(require_auth)])
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
async def get_thread(
    thread_id: str = PathParam(description="Thread identifier"),
    user_id: str = Depends(verify_resource_owner)
):
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
    user_id: str = Depends(verify_resource_owner)
):
    """Get list of files in a session."""
    try:
        files = storage.get_session_files(thread_id, session_id)
        return SessionFilesResponse(
            thread_id=thread_id, session_id=session_id, files=files
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.get("/threads/{thread_id}/sessions/{session_id}/files/{file_path:path}")
async def get_file(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session"),
    user_id: str = Depends(verify_resource_owner)
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
    "/threads/{thread_id}/sessions/{session_id}/files/{file_path:path}",
    response_model=FileOperationResponse,
)
async def create_or_update_file(
    file_content: FileContent,
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session"),
    user_id: str = Depends(verify_resource_owner)
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
    "/threads/{thread_id}/sessions/{session_id}/files/{file_path:path}",
    response_model=FileOperationResponse,
)
async def delete_file(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session"),
    user_id: str = Depends(verify_resource_owner)
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
    user_id: str = Depends(verify_resource_owner)
):
    """Delete an entire session with all files."""
    try:
        storage.delete_session(thread_id, session_id)
        return FileOperationResponse(message="Session deleted")
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete("/threads/{thread_id}", response_model=FileOperationResponse)
async def delete_thread(
    thread_id: str = PathParam(description="Thread identifier"),
    user_id: str = Depends(verify_resource_owner)
):
    """Delete an entire thread with all sessions."""
    try:
        storage.delete_thread(thread_id)
        return FileOperationResponse(message="Thread deleted")
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


# Export API Endpoints
# NOTE: These MUST be defined BEFORE the generic file path routes below
# to avoid route conflicts

# Store user settings in memory (in production, use a database)
user_settings = {}


@app.get("/threads/{thread_id}/sessions/{session_id}/export/single")
async def export_single_document(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    document_name: str = Query(description="Document name to export"),
    format: ExportFormat = Query(ExportFormat.MARKDOWN, description="Export format"),
    user_id: str = Depends(verify_resource_owner)
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
    user_id: str = Depends(verify_resource_owner)
):
    """Export a package of documents as ZIP archive."""
    logger.info(f"Export package request: thread_id={thread_id}, session_id={session_id}, package_type={package_type}, format={format}, user_id={user_id}")
    
    try:
        # Log storage base path
        logger.debug(f"Storage base path: {storage.base_path}")
        
        # Check if session exists
        session_path = storage.base_path / thread_id / "sessions" / session_id
        logger.debug(f"Checking session path: {session_path}")
        
        if not session_path.exists():
            logger.error(f"Session path does not exist: {session_path}")
            raise FileNotFoundError(f"Session not found: {session_id}")
        
        # List files in session
        files = list(session_path.iterdir())
        logger.debug(f"Files in session: {[f.name for f in files]}")
        
        # Use ZIP exporter
        zip_exporter = ZIPExporter(storage.base_path)
        logger.debug(f"Created ZIPExporter with base_path: {storage.base_path}")
        
        # Export package
        content = await zip_exporter.export_session_archive(
            thread_id, session_id, package_type, format
        )
        logger.info(f"Successfully exported package, size: {len(content)} bytes")
        
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
        logger.error(f"File not found during export: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Export failed with exception: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@app.get("/users/{user_id}/sessions/recent", response_model=List[SessionSummary])
async def get_recent_sessions(
    user_id: str = PathParam(description="User identifier"),
    limit: int = Query(5, max=5, description="Maximum number of sessions"),
    auth_user_id: str = Depends(require_auth)
):
    """Get list of recent sessions for export."""
    # Verify user can only access their own sessions
    if user_id != auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to other users' sessions is forbidden"
        )
    
    try:
        # Get user's thread (thread_id equals user_id in our system)
        threads_to_check = []
        try:
            thread_info = storage.get_thread_info(user_id)
            threads_to_check = [thread_info]
        except:
            # User has no threads yet
            return []
        
        sessions_list = []
        for thread in threads_to_check:
            for session in thread.sessions[:limit]:
                # Create session summary
                summary = SessionSummary(
                    thread_id=thread.thread_id,
                    session_id=session.session_id,
                    input_content=session.input_content,
                    question_preview=session.input_content[:30] + "..." 
                        if len(session.input_content) > 30 else session.input_content,
                    display_name=f"{session.input_content[:30]}... - {session.created.strftime('%d.%m.%Y')}",
                    created_at=session.created,
                    has_synthesized=False,  # Check if synthesized_material.md exists
                    has_questions=False,     # Check if questions.md exists
                    answers_count=0          # Count answer files
                )
                sessions_list.append(summary)
                
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
    user_id: str = PathParam(description="User identifier"),
    auth_user_id: str = Depends(require_auth)
):
    """Get user export settings."""
    # Verify user can only access their own settings
    if user_id != auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to other users' settings is forbidden"
        )
    
    # Return existing settings or create default
    if user_id not in user_settings:
        user_settings[user_id] = ExportSettings(user_id=user_id)
    
    return user_settings[user_id]


@app.put("/users/{user_id}/export-settings", response_model=ExportSettings)
async def update_export_settings(
    user_id: str = PathParam(description="User identifier"),
    settings: ExportSettings = ...,
    auth_user_id: str = Depends(require_auth)
):
    """Update user export settings."""
    # Verify user can only update their own settings
    if user_id != auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to other users' settings is forbidden"
        )
    
    settings.user_id = user_id
    settings.modified = datetime.now()
    user_settings[user_id] = settings
    return settings


def main():
    """Main entry point for running the server."""
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
