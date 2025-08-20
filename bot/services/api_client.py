"""HTTP API client for interacting with LearnFlow FastAPI service"""

import logging
from typing import Dict, Any, Optional
import aiohttp
import asyncio
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class HITLConfig(BaseModel):
    """HITL Configuration model for the bot side"""
    edit_material: bool = True
    generating_questions: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HITLConfig":
        """Create from dictionary"""
        return cls(**data)


class LearnFlowAPIClient:
    """HTTP client for interacting with FastAPI service"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=30)
        logger.info(f"Initialized LearnFlowAPIClient with base_url: {self.base_url}")
    
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
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to the API"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            logger.debug(f"Making {method} request to {url}")
            if json_data:
                logger.debug(f"Request data: {json_data}")
            
            async with session.request(method, url, json=json_data) as response:
                response_text = await response.text()
                logger.debug(f"Response status: {response.status}, body: {response_text}")
                
                if response.status >= 400:
                    logger.error(f"API request failed: {response.status} - {response_text}")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=response_text
                    )
                
                return await response.json()
                
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error for {method} {url}: {e}")
            raise
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {method} {url}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {method} {url}: {e}")
            raise
    
    async def get_hitl_config(self, user_id: int) -> HITLConfig:
        """
        Get current HITL configuration for user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            HITLConfig: Current HITL configuration
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            thread_id = str(user_id)
            response = await self._make_request("GET", f"/api/hitl/{thread_id}")
            return HITLConfig.from_dict(response)
            
        except Exception as e:
            logger.error(f"Failed to get HITL config for user {user_id}: {e}")
            # Return default config on error
            return HITLConfig()
    
    async def update_hitl_config(self, user_id: int, config: HITLConfig) -> HITLConfig:
        """
        Update full HITL configuration
        
        Args:
            user_id: Telegram user ID
            config: New HITL configuration
            
        Returns:
            HITLConfig: Updated HITL configuration
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            thread_id = str(user_id)
            response = await self._make_request(
                "PUT", 
                f"/api/hitl/{thread_id}", 
                config.to_dict()
            )
            return HITLConfig.from_dict(response)
            
        except Exception as e:
            logger.error(f"Failed to update HITL config for user {user_id}: {e}")
            raise
    
    async def toggle_node_hitl(self, user_id: int, node_name: str) -> HITLConfig:
        """
        Toggle HITL for a specific node
        
        Args:
            user_id: Telegram user ID
            node_name: Name of the node
            
        Returns:
            HITLConfig: Updated HITL configuration
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            thread_id = str(user_id)
            
            # First get current config to determine current state
            current_config = await self.get_hitl_config(user_id)
            current_enabled = getattr(current_config, node_name, False)
            new_enabled = not current_enabled
            
            response = await self._make_request(
                "PATCH", 
                f"/api/hitl/{thread_id}/node/{node_name}",
                {"enabled": new_enabled}
            )
            return HITLConfig.from_dict(response)
            
        except Exception as e:
            logger.error(f"Failed to toggle node {node_name} for user {user_id}: {e}")
            raise
    
    async def update_node_hitl(self, user_id: int, node_name: str, enabled: bool) -> HITLConfig:
        """
        Update HITL setting for a specific node
        
        Args:
            user_id: Telegram user ID
            node_name: Name of the node
            enabled: Whether to enable HITL for this node
            
        Returns:
            HITLConfig: Updated HITL configuration
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            thread_id = str(user_id)
            response = await self._make_request(
                "PATCH", 
                f"/api/hitl/{thread_id}/node/{node_name}",
                {"enabled": enabled}
            )
            return HITLConfig.from_dict(response)
            
        except Exception as e:
            logger.error(f"Failed to update node {node_name} to {enabled} for user {user_id}: {e}")
            raise
    
    async def bulk_update_hitl(self, user_id: int, enable_all: bool) -> HITLConfig:
        """
        Enable/disable HITL for all nodes
        
        Args:
            user_id: Telegram user ID
            enable_all: Whether to enable HITL for all nodes
            
        Returns:
            HITLConfig: Updated HITL configuration
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            thread_id = str(user_id)
            response = await self._make_request(
                "POST", 
                f"/api/hitl/{thread_id}/bulk",
                {"enable_all": enable_all}
            )
            return HITLConfig.from_dict(response)
            
        except Exception as e:
            logger.error(f"Failed to bulk update HITL to {enable_all} for user {user_id}: {e}")
            raise
    
    async def reset_hitl_config(self, user_id: int) -> HITLConfig:
        """
        Reset HITL configuration to defaults
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            HITLConfig: Reset HITL configuration
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            thread_id = str(user_id)
            response = await self._make_request("POST", f"/api/hitl/{thread_id}/reset")
            return HITLConfig.from_dict(response)
            
        except Exception as e:
            logger.error(f"Failed to reset HITL config for user {user_id}: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the API service is healthy
        
        Returns:
            Dict: Health check response
            
        Raises:
            aiohttp.ClientError: On HTTP request errors
        """
        try:
            response = await self._make_request("GET", "/health")
            return response
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise


# Global API client instance
_api_client_instance: Optional[LearnFlowAPIClient] = None


def get_api_client(base_url: str = None) -> LearnFlowAPIClient:
    """
    Get singleton API client instance
    
    Args:
        base_url: Base URL for the API service (if None, uses settings)
        
    Returns:
        LearnFlowAPIClient instance
    """
    global _api_client_instance
    if _api_client_instance is None:
        if base_url is None:
            # Import here to avoid circular imports
            try:
                from ..settings import get_settings
                settings = get_settings()
                base_url = f"http://{settings.api.learnflow_host}:{settings.api.learnflow_port}"
            except ImportError:
                base_url = "http://localhost:8000"
        _api_client_instance = LearnFlowAPIClient(base_url)
    return _api_client_instance


async def close_api_client():
    """Close the global API client session"""
    global _api_client_instance
    if _api_client_instance:
        await _api_client_instance.close()
        _api_client_instance = None