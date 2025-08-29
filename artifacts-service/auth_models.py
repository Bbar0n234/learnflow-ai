"""Authentication database models."""

from datetime import datetime
from sqlalchemy import Column, String, BigInteger, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AuthCode(Base):
    """Temporary authorization codes for web UI access."""
    
    __tablename__ = "auth_codes"
    
    username = Column(String(255), primary_key=True)
    code = Column(String(10), primary_key=True)
    user_id = Column(BigInteger, nullable=False)  # Telegram user ID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_auth_codes_created_at", "created_at"),
    )