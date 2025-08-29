"""Database operations for auth codes."""

import asyncpg
import string
import random
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AuthDatabase:
    """Handle auth code operations in PostgreSQL."""
    
    def __init__(self, database_url: str):
        """Initialize database connection settings."""
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    
    async def disconnect(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    @staticmethod
    def generate_code(length: int = 6) -> str:
        """Generate random alphanumeric code."""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    async def create_auth_code(self, username: str, user_id: int) -> str:
        """Create new auth code for user."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        code = self.generate_code()
        
        async with self.pool.acquire() as conn:
            try:
                # Delete old codes for this user
                await conn.execute(
                    "DELETE FROM auth_codes WHERE username = $1",
                    username
                )
                
                # Insert new code
                await conn.execute(
                    """
                    INSERT INTO auth_codes (username, code, user_id, created_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    username,
                    code,
                    user_id,
                    datetime.utcnow()
                )
                
                logger.info(f"Created auth code for user {username} (ID: {user_id})")
                return code
                
            except Exception as e:
                logger.error(f"Failed to create auth code: {e}")
                raise
    
    async def verify_code(self, username: str, code: str) -> Optional[int]:
        """Verify auth code and return user_id if valid."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            try:
                # Check if code exists and is not expired (5 minutes)
                result = await conn.fetchrow(
                    """
                    SELECT user_id FROM auth_codes
                    WHERE username = $1 
                    AND code = $2
                    AND created_at > $3
                    """,
                    username,
                    code,
                    datetime.utcnow() - timedelta(minutes=5)
                )
                
                if result:
                    # Delete used code
                    await conn.execute(
                        "DELETE FROM auth_codes WHERE username = $1 AND code = $2",
                        username,
                        code
                    )
                    logger.info(f"Verified and deleted auth code for user {username}")
                    return result['user_id']
                
                return None
                
            except Exception as e:
                logger.error(f"Failed to verify auth code: {e}")
                raise
    
    async def cleanup_expired_codes(self):
        """Remove expired auth codes from database."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            try:
                deleted = await conn.execute(
                    """
                    DELETE FROM auth_codes
                    WHERE created_at < $1
                    """,
                    datetime.utcnow() - timedelta(minutes=5)
                )
                
                count = int(deleted.split()[-1]) if deleted else 0
                if count > 0:
                    logger.info(f"Cleaned up {count} expired auth codes")
                    
            except Exception as e:
                logger.error(f"Failed to cleanup expired codes: {e}")
                raise