"""HTTP API client for interacting with Artifacts Service with authentication."""

import logging
from typing import Dict, Any, Optional, List
import aiohttp
import asyncio

from ..settings import get_settings

logger = logging.getLogger(__name__)


class ArtifactsAPIClient:
    """HTTP client for interacting with Artifacts Service."""

    def __init__(self, base_url: str = None, api_key: str = None, timeout: int = 30):
        settings = get_settings()
        self.base_url = (base_url or settings.artifacts_service_url).rstrip("/")
        self.api_key = api_key or settings.bot_api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        logger.info(f"Initialized ArtifactsAPIClient with base_url: {self.base_url}")
        if self.api_key:
            logger.info(f"API key configured: {self.api_key[:8]}...")
        else:
            logger.warning("No API key configured for ArtifactsAPIClient")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _get_auth_headers(self, user_id: int) -> Dict[str, str]:
        """Get authentication headers for requests."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["X-User-Id"] = str(user_id)
        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        user_id: Optional[int] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Make HTTP request to the API with authentication."""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        headers = {}
        if user_id:
            headers = self._get_auth_headers(user_id)

        try:
            logger.debug(f"Making {method} request to {url}")
            if json_data:
                logger.debug(f"Request data: {json_data}")
            if headers:
                logger.debug(f"Auth headers present for user {user_id}: {headers}")
            else:
                logger.warning(f"No auth headers for request to {url}")

            async with session.request(
                method, 
                url, 
                json=json_data, 
                params=params,
                headers=headers
            ) as response:
                # Check if response is JSON
                content_type = response.headers.get('Content-Type', '')
                
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(
                        f"API request failed: {response.status} - {error_text}"
                    )
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=error_text,
                    )
                
                # Return appropriate response based on content type
                if 'application/json' in content_type:
                    return await response.json()
                elif 'application/zip' in content_type or 'application/pdf' in content_type:
                    return await response.read()
                else:
                    return await response.text()

        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error for {method} {url}: {e}")
            raise
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {method} {url}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {method} {url}: {e}")
            raise

    async def get_recent_sessions(
        self, user_id: int, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get recent sessions for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            
        Returns:
            List of session summaries
        """
        try:
            response = await self._make_request(
                "GET",
                f"/users/{user_id}/sessions/recent",
                user_id=user_id,
                params={"limit": limit}
            )
            return response
        except Exception as e:
            logger.error(f"Failed to get recent sessions for user {user_id}: {e}")
            return []

    async def export_single_document(
        self,
        user_id: int,
        session_id: str,
        document_name: str,
        format: str = "markdown"
    ) -> bytes:
        """
        Export a single document.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            document_name: Name of document to export
            format: Export format (markdown or pdf)
            
        Returns:
            Document content as bytes
        """
        try:
            response = await self._make_request(
                "GET",
                f"/threads/{user_id}/sessions/{session_id}/export/single",
                user_id=user_id,
                params={"document_name": document_name, "format": format}
            )
            
            # Convert to bytes if string
            if isinstance(response, str):
                return response.encode('utf-8')
            return response
            
        except Exception as e:
            logger.error(f"Failed to export document for user {user_id}: {e}")
            raise

    async def export_package(
        self,
        user_id: int,
        session_id: str,
        package_type: str = "final",
        format: str = "markdown"
    ) -> bytes:
        """
        Export a package of documents as ZIP.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            package_type: Package type (minimal, standard, full, final)
            format: Export format (markdown or pdf)
            
        Returns:
            ZIP archive content as bytes
        """
        try:
            response = await self._make_request(
                "GET",
                f"/threads/{user_id}/sessions/{session_id}/export/package",
                user_id=user_id,
                params={"package_type": package_type, "format": format}
            )
            return response
            
        except Exception as e:
            logger.error(f"Failed to export package for user {user_id}: {e}")
            raise

    async def get_export_settings(self, user_id: int) -> Dict[str, Any]:
        """
        Get export settings for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Export settings dictionary
        """
        try:
            response = await self._make_request(
                "GET",
                f"/users/{user_id}/export-settings",
                user_id=user_id
            )
            return response
        except Exception as e:
            logger.error(f"Failed to get export settings for user {user_id}: {e}")
            # Return defaults on error
            return {
                "user_id": str(user_id),
                "default_format": "markdown",
                "default_package": "final",
                "include_images": True
            }

    async def update_export_settings(
        self, user_id: int, settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update export settings for a user.
        
        Args:
            user_id: User identifier
            settings: New export settings
            
        Returns:
            Updated settings dictionary
        """
        try:
            response = await self._make_request(
                "PUT",
                f"/users/{user_id}/export-settings",
                user_id=user_id,
                json_data=settings
            )
            return response
        except Exception as e:
            logger.error(f"Failed to update export settings for user {user_id}: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the Artifacts service is healthy.
        
        Returns:
            Health check response
        """
        try:
            response = await self._make_request("GET", "/health")
            return response
        except Exception as e:
            logger.error(f"Artifacts service health check failed: {e}")
            raise


# Global API client instance
_artifacts_client_instance: Optional[ArtifactsAPIClient] = None


def get_artifacts_client() -> ArtifactsAPIClient:
    """
    Get singleton Artifacts API client instance.
    
    Returns:
        ArtifactsAPIClient instance
    """
    global _artifacts_client_instance
    if _artifacts_client_instance is None:
        # Increase timeout to 60 seconds for PDF generation
        _artifacts_client_instance = ArtifactsAPIClient(timeout=60)
    return _artifacts_client_instance


async def close_artifacts_client():
    """Close the global Artifacts API client session."""
    global _artifacts_client_instance
    if _artifacts_client_instance:
        await _artifacts_client_instance.close()
        _artifacts_client_instance = None