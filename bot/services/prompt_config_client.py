"""HTTP client for interacting with Prompt Configuration Service"""

import logging
from typing import Dict, Any, Optional, List
import aiohttp
import asyncio
from datetime import datetime, timedelta

from ..models.prompt_config import (
    Profile,
    ProfileWithSettings,
    Placeholder,
    PlaceholderValue,
    UserSettings,
    UserPlaceholderSetting,
    GeneratePromptRequest,
    GeneratePromptResponse,
)


logger = logging.getLogger(__name__)


class PromptConfigCache:
    """Simple in-memory cache for prompt config data"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[Any, datetime]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl_seconds):
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set value in cache with current timestamp"""
        self._cache[key] = (value, datetime.now())
    
    def invalidate(self, pattern: str = None):
        """Invalidate cache entries matching pattern or all if pattern is None"""
        if pattern is None:
            self._cache.clear()
        else:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]


class PromptConfigClient:
    """HTTP client for Prompt Configuration Service"""
    
    def __init__(self, base_url: str = "http://localhost:8002", cache_ttl: int = 300):
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.cache = PromptConfigCache(ttl_seconds=cache_ttl)
        logger.info(f"Initialized PromptConfigClient with base_url: {self.base_url}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session
    
    async def close(self):
        """Close the HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Make HTTP request to the API with retry logic"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        retry_count = 3
        retry_delay = 1.0
        
        for attempt in range(retry_count):
            try:
                logger.debug(f"Making {method} request to {url} (attempt {attempt + 1})")
                
                async with session.request(
                    method, url, json=json_data, params=params
                ) as response:
                    response_text = await response.text()
                    logger.debug(f"Response status: {response.status}")
                    
                    if response.status >= 400:
                        logger.error(
                            f"API request failed: {response.status} - {response_text}"
                        )
                        if response.status >= 500 and attempt < retry_count - 1:
                            await asyncio.sleep(retry_delay * (2 ** attempt))
                            continue
                        
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=response_text,
                        )
                    
                    return await response.json() if response_text else {}
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Request error for {method} {url}: {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                raise
            except Exception as e:
                logger.error(f"Unexpected error for {method} {url}: {e}")
                raise
    
    async def get_profiles(self, category: Optional[str] = None) -> List[Profile]:
        """
        Get list of all available profiles
        
        Args:
            category: Optional category filter (style/subject)
        
        Returns:
            List of Profile objects
        """
        cache_key = f"profiles:{category or 'all'}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            params = {"category": category} if category else None
            response = await self._make_request("GET", "/api/v1/profiles", params=params)
            
            profiles = [Profile(**p) for p in response]
            self.cache.set(cache_key, profiles)
            return profiles
        
        except Exception as e:
            logger.error(f"Failed to get profiles: {e}")
            return []
    
    async def get_user_placeholders(self, user_id: int) -> UserSettings:
        """
        Get user's current placeholder settings
        
        Args:
            user_id: User ID
        
        Returns:
            UserSettings object with current configuration
        """
        try:
            response = await self._make_request(
                "GET", f"/api/v1/users/{user_id}/placeholders"
            )
            
            # Parse the response into UserSettings
            placeholders = {}
            for name, data in response.get("placeholders", {}).items():
                placeholders[name] = UserPlaceholderSetting(
                    placeholder_id=data.get("placeholder_id", ""),
                    placeholder_name=name,
                    placeholder_display_name=data.get("placeholder_display_name", name),
                    value_id=data.get("value_id", ""),
                    value=data.get("value", ""),
                    display_name=data.get("display_name", data.get("value", ""))
                )
            
            return UserSettings(
                user_id=user_id,
                placeholders=placeholders,
                active_profile_id=response.get("active_profile_id"),
                active_profile_name=response.get("active_profile_name")
            )
        
        except Exception as e:
            logger.error(f"Failed to get user placeholders for {user_id}: {e}")
            return UserSettings(user_id=user_id)
    
    async def apply_profile(self, user_id: int, profile_id: str) -> UserSettings:
        """
        Apply a profile to user's configuration
        
        Args:
            user_id: User ID
            profile_id: Profile ID to apply
        
        Returns:
            Updated UserSettings
        """
        try:
            # Invalidate user cache
            self.cache.invalidate(f"user:{user_id}")
            
            response = await self._make_request(
                "POST", f"/api/v1/users/{user_id}/apply-profile/{profile_id}"
            )
            
            # Parse response
            placeholders = {}
            for name, data in response.get("placeholders", {}).items():
                placeholders[name] = UserPlaceholderSetting(
                    placeholder_id=data.get("placeholder_id", ""),
                    placeholder_name=name,
                    placeholder_display_name=data.get("placeholder_display_name", name),
                    value_id=data.get("value_id", ""),
                    value=data.get("value", ""),
                    display_name=data.get("display_name", data.get("value", ""))
                )
            
            return UserSettings(
                user_id=user_id,
                placeholders=placeholders,
                active_profile_id=response.get("active_profile_id"),
                active_profile_name=response.get("active_profile_name")
            )
        
        except Exception as e:
            logger.error(f"Failed to apply profile {profile_id} for user {user_id}: {e}")
            raise
    
    async def set_placeholder(
        self, user_id: int, placeholder_id: str, value_id: str
    ) -> UserPlaceholderSetting:
        """
        Set a specific placeholder value for user
        
        Args:
            user_id: User ID
            placeholder_id: Placeholder ID
            value_id: Value ID to set
        
        Returns:
            Updated placeholder setting
        """
        try:
            # Invalidate user cache
            self.cache.invalidate(f"user:{user_id}")
            
            response = await self._make_request(
                "PUT",
                f"/api/v1/users/{user_id}/placeholders/{placeholder_id}",
                {"value_id": value_id}
            )
            
            return UserPlaceholderSetting(
                placeholder_id=response.get("placeholder_id", placeholder_id),
                placeholder_name=response.get("placeholder_name", ""),
                placeholder_display_name=response.get("placeholder_display_name", ""),
                value_id=response.get("value_id", value_id),
                value=response.get("value", ""),
                display_name=response.get("display_name", "")
            )
        
        except Exception as e:
            logger.error(
                f"Failed to set placeholder {placeholder_id} to {value_id} for user {user_id}: {e}"
            )
            raise
    
    async def get_placeholder_values(self, placeholder_id: str) -> List[PlaceholderValue]:
        """
        Get available values for a placeholder
        
        Args:
            placeholder_id: Placeholder ID
        
        Returns:
            List of available PlaceholderValue objects
        """
        cache_key = f"placeholder_values:{placeholder_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        try:
            response = await self._make_request(
                "GET", f"/api/v1/placeholders/{placeholder_id}/values"
            )
            
            values = [PlaceholderValue(**v) for v in response]
            self.cache.set(cache_key, values)
            return values
        
        except Exception as e:
            logger.error(f"Failed to get values for placeholder {placeholder_id}: {e}")
            return []
    
    async def reset_to_defaults(self, user_id: int) -> UserSettings:
        """
        Reset user's configuration to defaults
        
        Args:
            user_id: User ID
        
        Returns:
            Reset UserSettings
        """
        try:
            # Invalidate user cache
            self.cache.invalidate(f"user:{user_id}")
            
            response = await self._make_request(
                "POST", f"/api/v1/users/{user_id}/reset"
            )
            
            # Parse response
            placeholders = {}
            for name, data in response.get("placeholders", {}).items():
                placeholders[name] = UserPlaceholderSetting(
                    placeholder_id=data.get("placeholder_id", ""),
                    placeholder_name=name,
                    placeholder_display_name=data.get("placeholder_display_name", name),
                    value_id=data.get("value_id", ""),
                    value=data.get("value", ""),
                    display_name=data.get("display_name", data.get("value", ""))
                )
            
            return UserSettings(
                user_id=user_id,
                placeholders=placeholders,
                active_profile_id=None,
                active_profile_name=None
            )
        
        except Exception as e:
            logger.error(f"Failed to reset settings for user {user_id}: {e}")
            raise
    
    async def health_check(self) -> bool:
        """
        Check if the Prompt Config Service is healthy
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            await self._make_request("GET", "/health")
            return True
        except Exception as e:
            logger.error(f"Prompt Config Service health check failed: {e}")
            return False


# Global client instance
_prompt_config_client: Optional[PromptConfigClient] = None


def get_prompt_config_client(base_url: str = None) -> PromptConfigClient:
    """
    Get singleton prompt config client instance
    
    Args:
        base_url: Base URL for the service (if None, uses settings)
    
    Returns:
        PromptConfigClient instance
    """
    global _prompt_config_client
    if _prompt_config_client is None:
        if base_url is None:
            # Import here to avoid circular imports
            try:
                from ..settings import get_settings
                settings = get_settings()
                base_url = settings.prompt_service.url
                cache_ttl = settings.prompt_service.cache_ttl
            except ImportError:
                base_url = "http://localhost:8002"
                cache_ttl = 300
        else:
            cache_ttl = 300
        _prompt_config_client = PromptConfigClient(base_url, cache_ttl)
    return _prompt_config_client


async def close_prompt_config_client():
    """Close the global prompt config client session"""
    global _prompt_config_client
    if _prompt_config_client:
        await _prompt_config_client.close()
        _prompt_config_client = None