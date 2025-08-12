"""FastAPI application for Artifacts Service."""

from typing import Union

from fastapi import FastAPI, HTTPException, status, Path as PathParam
from fastapi.responses import PlainTextResponse, JSONResponse
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
)
from .exceptions import ArtifactsServiceException, map_to_http_exception
from .settings import settings


# Global storage instance
storage = ArtifactsStorage()


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
    lifespan=lifespan
)


@app.exception_handler(ArtifactsServiceException)
async def service_exception_handler(request, exc: ArtifactsServiceException):
    """Handle service exceptions."""
    http_exc = map_to_http_exception(exc)
    return JSONResponse(
        status_code=http_exc.status_code,
        content=ErrorResponse(error=str(exc)).model_dump()
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
            detail=f"Service unavailable: {str(e)}"
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
            detail=f"Failed to get threads: {str(e)}"
        )


@app.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: str = PathParam(description="Thread identifier")
):
    """Get information about a specific thread."""
    try:
        thread_info = storage.get_thread_info(thread_id)
        return ThreadDetailResponse(
            thread_id=thread_info.thread_id,
            sessions=thread_info.sessions,
            created=thread_info.created,
            last_activity=thread_info.last_activity,
            sessions_count=thread_info.sessions_count
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.get("/threads/{thread_id}/sessions/{session_id}", response_model=SessionFilesResponse)
async def get_session_files(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier")
):
    """Get list of files in a session."""
    try:
        files = storage.get_session_files(thread_id, session_id)
        return SessionFilesResponse(
            thread_id=thread_id,
            session_id=session_id,
            files=files
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.get("/threads/{thread_id}/sessions/{session_id}/{file_path:path}")
async def get_file(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session")
):
    """Get file content."""
    try:
        content = storage.read_file(thread_id, session_id, file_path)
        
        # Determine response type based on file extension
        if file_path.endswith('.json'):
            return JSONResponse(content=content)
        else:
            return PlainTextResponse(content=content, media_type="text/plain")
            
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.post("/threads/{thread_id}/sessions/{session_id}/{file_path:path}", 
          response_model=FileOperationResponse)
async def create_or_update_file(
    file_content: FileContent,
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session")
):
    """Create or update a file in a session."""
    try:
        # Check if file already exists
        file_exists = False
        try:
            storage.read_file(thread_id, session_id, file_path)
            file_exists = True
        except:
            pass
        
        # Write the file
        storage.write_file(
            thread_id=thread_id,
            session_id=session_id,
            path=file_path,
            content=file_content.content,
            content_type=file_content.content_type
        )
        
        if file_exists:
            return FileOperationResponse(
                message="File updated",
                path=file_path
            )
        else:
            return FileOperationResponse(
                message="File created",
                path=file_path
            )
            
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete("/threads/{thread_id}/sessions/{session_id}/{file_path:path}",
            response_model=FileOperationResponse)
async def delete_file(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier"),
    file_path: str = PathParam(description="File path relative to session")
):
    """Delete a file from a session."""
    try:
        storage.delete_file(thread_id, session_id, file_path)
        return FileOperationResponse(
            message="File deleted",
            path=file_path
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete("/threads/{thread_id}/sessions/{session_id}",
            response_model=FileOperationResponse)
async def delete_session(
    thread_id: str = PathParam(description="Thread identifier"),
    session_id: str = PathParam(description="Session identifier")
):
    """Delete an entire session with all files."""
    try:
        storage.delete_session(thread_id, session_id)
        return FileOperationResponse(
            message="Session deleted"
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


@app.delete("/threads/{thread_id}",
            response_model=FileOperationResponse)
async def delete_thread(
    thread_id: str = PathParam(description="Thread identifier")
):
    """Delete an entire thread with all sessions."""
    try:
        storage.delete_thread(thread_id)
        return FileOperationResponse(
            message="Thread deleted"
        )
    except ArtifactsServiceException as e:
        raise map_to_http_exception(e)


def main():
    """Main entry point for running the server."""
    import uvicorn
    
    uvicorn.run(
        "artifacts-service.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )


if __name__ == "__main__":
    main()