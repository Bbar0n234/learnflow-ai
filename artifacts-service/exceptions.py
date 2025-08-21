"""Custom exceptions for Artifacts Service."""

from fastapi import HTTPException, status


class ArtifactsServiceException(Exception):
    """Base exception for artifacts service."""

    pass


class ThreadNotFoundException(ArtifactsServiceException):
    """Raised when thread is not found."""

    pass


class SessionNotFoundException(ArtifactsServiceException):
    """Raised when session is not found."""

    pass


class FileNotFoundException(ArtifactsServiceException):
    """Raised when file is not found."""

    pass


class InvalidPathException(ArtifactsServiceException):
    """Raised when path is invalid or unsafe."""

    pass


class FileTooBigException(ArtifactsServiceException):
    """Raised when file exceeds size limit."""

    pass


class TooManyFilesException(ArtifactsServiceException):
    """Raised when thread has too many files."""

    pass


class UnsupportedContentTypeException(ArtifactsServiceException):
    """Raised when content type is not supported."""

    pass


# HTTP exception mappers
def map_to_http_exception(exc: ArtifactsServiceException) -> HTTPException:
    """Map service exceptions to HTTP exceptions."""
    if isinstance(
        exc, (ThreadNotFoundException, SessionNotFoundException, FileNotFoundException)
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    elif isinstance(
        exc,
        (
            InvalidPathException,
            FileTooBigException,
            TooManyFilesException,
            UnsupportedContentTypeException,
        ),
    ):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    else:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
