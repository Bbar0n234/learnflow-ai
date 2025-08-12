"""Pydantic models for Artifacts Service."""

from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """Information about a file in a session."""
    path: str = Field(description="Relative path to the file")
    size: int = Field(description="File size in bytes")
    modified: datetime = Field(description="Last modification time")
    content_type: str = Field(description="MIME content type")


class FileContent(BaseModel):
    """Request model for file content."""
    content: str = Field(description="File content as string")
    content_type: str = Field(
        default="text/markdown",
        description="MIME content type"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata"
    )


class SessionInfo(BaseModel):
    """Information about a session."""
    session_id: str = Field(description="Unique session identifier")
    exam_question: str = Field(description="Exam question text")
    created: datetime = Field(description="Session creation time")
    modified: datetime = Field(description="Last modification time")
    status: str = Field(description="Session status (active, completed, failed)")
    files_count: int = Field(description="Number of files in session")


class SessionMetadata(BaseModel):
    """Complete session metadata."""
    session_id: str = Field(description="Unique session identifier")
    thread_id: str = Field(description="Thread identifier")
    exam_question: str = Field(description="Exam question text")
    created: datetime = Field(description="Session creation time")
    modified: datetime = Field(description="Last modification time")
    status: str = Field(
        default="active",
        description="Session status (active, completed, failed)"
    )
    workflow_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Data from ExamState workflow"
    )


class ThreadInfo(BaseModel):
    """Information about a thread."""
    thread_id: str = Field(description="Unique thread identifier")
    sessions: List[SessionInfo] = Field(description="List of sessions in thread")
    created: datetime = Field(description="Thread creation time")
    last_activity: datetime = Field(description="Last activity timestamp")
    sessions_count: int = Field(description="Number of sessions in thread")


class ThreadMetadata(BaseModel):
    """Complete thread metadata."""
    thread_id: str = Field(description="Unique thread identifier")
    created: datetime = Field(description="Thread creation time")
    last_activity: datetime = Field(description="Last activity timestamp")
    sessions_count: int = Field(description="Number of sessions in thread")
    user_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Information about the Telegram user"
    )


# Response models
class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(description="Service status")
    service: str = Field(default="artifacts-service", description="Service name")
    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")


class ThreadsListResponse(BaseModel):
    """Response for threads list endpoint."""
    threads: List[ThreadInfo] = Field(description="List of threads")


class ThreadDetailResponse(BaseModel):
    """Response for thread detail endpoint."""
    thread_id: str = Field(description="Thread identifier")
    sessions: List[SessionInfo] = Field(description="List of sessions")
    created: datetime = Field(description="Thread creation time")
    last_activity: datetime = Field(description="Last activity timestamp")
    sessions_count: int = Field(description="Number of sessions")


class SessionFilesResponse(BaseModel):
    """Response for session files endpoint."""
    thread_id: str = Field(description="Thread identifier")
    session_id: str = Field(description="Session identifier")
    files: List[FileInfo] = Field(description="List of files in session")


class FileOperationResponse(BaseModel):
    """Response for file operations."""
    message: str = Field(description="Operation result message")
    path: Optional[str] = Field(default=None, description="File path")
    timestamp: datetime = Field(default_factory=datetime.now, description="Operation timestamp")


class ErrorResponse(BaseModel):
    """Error response."""
    error: str = Field(description="Error message")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")