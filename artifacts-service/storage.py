"""File storage operations for Artifacts Service."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import re

from .exceptions import (
    ThreadNotFoundException,
    SessionNotFoundException,
    FileNotFoundException,
    InvalidPathException,
    FileTooBigException,
    TooManyFilesException,
    UnsupportedContentTypeException,
)
from .models import ThreadInfo, SessionInfo, SessionMetadata, FileInfo, ThreadMetadata
from .settings import settings


class ArtifactsStorage:
    """File storage system for LearnFlow AI artifacts."""

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize storage with base path."""
        self.base_path = base_path or settings.data_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def validate_thread_id(self, thread_id: str) -> bool:
        """Validate thread_id format."""
        if not thread_id or not isinstance(thread_id, str):
            return False
        # Allow alphanumeric characters, hyphens, underscores
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", thread_id)) and len(thread_id) <= 64

    def validate_session_id(self, session_id: str) -> bool:
        """Validate session_id format."""
        if not session_id or not isinstance(session_id, str):
            return False
        # Allow alphanumeric characters, hyphens, underscores (UUID format)
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", session_id)) and len(session_id) <= 64

    def validate_path(self, path: str) -> bool:
        """Validate file path for security."""
        if not path or not isinstance(path, str):
            return False

        # Check for path traversal attempts
        if ".." in path or path.startswith("/") or "\\" in path:
            return False

        # Check path depth
        parts = [p for p in path.split("/") if p]
        if len(parts) > settings.max_path_depth:
            return False

        # Check for valid characters
        for part in parts:
            if not re.match(r"^[a-zA-Z0-9._-]+$", part):
                return False

        return True

    def _get_thread_path(self, thread_id: str) -> Path:
        """Get thread directory path."""
        if not self.validate_thread_id(thread_id):
            raise InvalidPathException(f"Invalid thread_id: {thread_id}")
        return self.base_path / thread_id

    def _get_session_path(self, thread_id: str, session_id: str) -> Path:
        """Get session directory path."""
        if not self.validate_session_id(session_id):
            raise InvalidPathException(f"Invalid session_id: {session_id}")
        return self._get_thread_path(thread_id) / "sessions" / session_id

    def _get_file_path(self, thread_id: str, session_id: str, path: str) -> Path:
        """Get full file path."""
        if not self.validate_path(path):
            raise InvalidPathException(f"Invalid file path: {path}")
        return self._get_session_path(thread_id, session_id) / path

    def create_thread_directory(self, thread_id: str) -> Path:
        """Create thread directory structure."""
        thread_path = self._get_thread_path(thread_id)
        thread_path.mkdir(parents=True, exist_ok=True)
        (thread_path / "sessions").mkdir(exist_ok=True)

        # Create thread metadata if it doesn't exist
        metadata_path = thread_path / "metadata.json"
        if not metadata_path.exists():
            metadata = ThreadMetadata(
                thread_id=thread_id,
                created=datetime.now(),
                last_activity=datetime.now(),
                sessions_count=0,
            )
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata.model_dump(), f, indent=2, default=str)

        return thread_path

    def create_session_directory(self, thread_id: str, session_id: str) -> Path:
        """Create session directory structure."""
        # Ensure thread exists
        self.create_thread_directory(thread_id)

        session_path = self._get_session_path(thread_id, session_id)
        session_path.mkdir(parents=True, exist_ok=True)
        (session_path / "answers").mkdir(exist_ok=True)

        return session_path

    def get_threads(self) -> List[ThreadInfo]:
        """Get list of all threads."""
        threads = []

        if not self.base_path.exists():
            return threads

        for thread_dir in self.base_path.iterdir():
            if thread_dir.is_dir() and self.validate_thread_id(thread_dir.name):
                try:
                    thread_info = self.get_thread_info(thread_dir.name)
                    threads.append(thread_info)
                except ThreadNotFoundException:
                    continue

        return sorted(threads, key=lambda x: x.last_activity, reverse=True)

    def get_thread_info(self, thread_id: str) -> ThreadInfo:
        """Get thread information."""
        thread_path = self._get_thread_path(thread_id)

        if not thread_path.exists():
            raise ThreadNotFoundException(f"Thread {thread_id} not found")

        # Get thread metadata
        metadata_path = thread_path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata_data = json.load(f)
            metadata = ThreadMetadata(**metadata_data)
        else:
            # Create default metadata
            metadata = ThreadMetadata(
                thread_id=thread_id,
                created=datetime.now(),
                last_activity=datetime.now(),
                sessions_count=0,
            )

        # Get sessions
        sessions = []
        sessions_dir = thread_path / "sessions"
        if sessions_dir.exists():
            for session_dir in sessions_dir.iterdir():
                if session_dir.is_dir() and self.validate_session_id(session_dir.name):
                    try:
                        session_metadata = self.get_session_metadata(
                            thread_id, session_dir.name
                        )
                        sessions.append(
                            SessionInfo(
                                session_id=session_metadata.session_id,
                                exam_question=session_metadata.exam_question,
                                display_name=session_metadata.display_name,
                                created=session_metadata.created,
                                modified=session_metadata.modified,
                                status=session_metadata.status,
                                files_count=len(list(session_dir.rglob("*")))
                                if session_dir.exists()
                                else 0,
                            )
                        )
                    except SessionNotFoundException:
                        continue

        return ThreadInfo(
            thread_id=thread_id,
            sessions=sorted(sessions, key=lambda x: x.created, reverse=True),
            created=metadata.created,
            last_activity=metadata.last_activity,
            sessions_count=len(sessions),
        )

    def get_session_files(self, thread_id: str, session_id: str) -> List[FileInfo]:
        """Get list of files in session."""
        session_path = self._get_session_path(thread_id, session_id)

        if not session_path.exists():
            raise SessionNotFoundException(
                f"Session {session_id} not found in thread {thread_id}"
            )

        files = []
        for file_path in session_path.rglob("*"):
            if file_path.is_file() and not file_path.name.endswith(".json"):
                relative_path = file_path.relative_to(session_path)
                stat = file_path.stat()

                files.append(
                    FileInfo(
                        path=str(relative_path),
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        content_type=self._guess_content_type(file_path),
                    )
                )

        return sorted(files, key=lambda x: x.modified, reverse=True)

    def get_session_metadata(self, thread_id: str, session_id: str) -> SessionMetadata:
        """Get session metadata."""
        session_path = self._get_session_path(thread_id, session_id)

        if not session_path.exists():
            raise SessionNotFoundException(
                f"Session {session_id} not found in thread {thread_id}"
            )

        metadata_path = session_path / "session_metadata.json"
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata_data = json.load(f)
            return SessionMetadata(**metadata_data)
        else:
            # Create default metadata
            return SessionMetadata(
                session_id=session_id,
                thread_id=thread_id,
                exam_question="",
                created=datetime.now(),
                modified=datetime.now(),
                status="active",
            )

    def update_session_metadata(
        self, thread_id: str, session_id: str, metadata: SessionMetadata
    ) -> bool:
        """Update session metadata."""
        session_path = self._get_session_path(thread_id, session_id)

        if not session_path.exists():
            raise SessionNotFoundException(
                f"Session {session_id} not found in thread {thread_id}"
            )

        metadata_path = session_path / "session_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata.model_dump(), f, indent=2, default=str)

        # Update thread last_activity
        self._update_thread_activity(thread_id)

        return True

    def read_file(self, thread_id: str, session_id: str, path: str) -> str:
        """Read file content."""
        file_path = self._get_file_path(thread_id, session_id, path)

        if not file_path.exists():
            raise FileNotFoundException(
                f"File {path} not found in session {session_id}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(
        self,
        thread_id: str,
        session_id: str,
        path: str,
        content: str,
        content_type: str = "text/markdown",
    ) -> bool:
        """Write file content."""
        # Validate content type
        if content_type not in settings.allowed_content_types:
            raise UnsupportedContentTypeException(
                f"Content type {content_type} not supported"
            )

        # Check file size
        if len(content.encode("utf-8")) > settings.max_file_size:
            raise FileTooBigException(
                f"File size exceeds limit of {settings.max_file_size} bytes"
            )

        # Check files count
        try:
            files = self.get_session_files(thread_id, session_id)
            if len(files) >= settings.max_files_per_thread:
                raise TooManyFilesException(
                    f"Too many files in thread (max: {settings.max_files_per_thread})"
                )
        except SessionNotFoundException:
            # Session doesn't exist yet, create it
            self.create_session_directory(thread_id, session_id)

        file_path = self._get_file_path(thread_id, session_id, path)

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Update session metadata
        try:
            session_metadata = self.get_session_metadata(thread_id, session_id)
            session_metadata.modified = datetime.now()
            self.update_session_metadata(thread_id, session_id, session_metadata)
        except SessionNotFoundException:
            pass

        return True

    def delete_file(self, thread_id: str, session_id: str, path: str) -> bool:
        """Delete file."""
        file_path = self._get_file_path(thread_id, session_id, path)

        if not file_path.exists():
            raise FileNotFoundException(
                f"File {path} not found in session {session_id}"
            )

        file_path.unlink()

        # Update session metadata
        try:
            session_metadata = self.get_session_metadata(thread_id, session_id)
            session_metadata.modified = datetime.now()
            self.update_session_metadata(thread_id, session_id, session_metadata)
        except SessionNotFoundException:
            pass

        return True

    def delete_session(self, thread_id: str, session_id: str) -> bool:
        """Delete entire session."""
        session_path = self._get_session_path(thread_id, session_id)

        if not session_path.exists():
            raise SessionNotFoundException(
                f"Session {session_id} not found in thread {thread_id}"
            )

        shutil.rmtree(session_path)

        # Update thread metadata
        self._update_thread_activity(thread_id)

        return True

    def delete_thread(self, thread_id: str) -> bool:
        """Delete entire thread."""
        thread_path = self._get_thread_path(thread_id)

        if not thread_path.exists():
            raise ThreadNotFoundException(f"Thread {thread_id} not found")

        shutil.rmtree(thread_path)
        return True

    def _update_thread_activity(self, thread_id: str) -> None:
        """Update thread last activity timestamp."""
        try:
            thread_path = self._get_thread_path(thread_id)
            metadata_path = thread_path / "metadata.json"

            if metadata_path.exists():
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata_data = json.load(f)
                metadata = ThreadMetadata(**metadata_data)
                metadata.last_activity = datetime.now()

                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata.model_dump(), f, indent=2, default=str)
        except Exception:
            # Don't fail if we can't update metadata
            pass

    def _guess_content_type(self, file_path: Path) -> str:
        """Guess content type from file extension."""
        suffix = file_path.suffix.lower()
        if suffix == ".md":
            return "text/markdown"
        elif suffix == ".json":
            return "application/json"
        else:
            return "text/plain"
