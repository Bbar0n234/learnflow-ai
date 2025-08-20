"""HITL Configuration Model for LearnFlow AI"""

from pydantic import BaseModel, Field
from typing import Dict, Any


class HITLConfig(BaseModel):
    """Simple HITL configuration with flags for each node"""
    
    # Flags for nodes (exact correspondence with names in graph.py)
    edit_material: bool = Field(
        default=True,
        description="Enable HITL for material editing node"
    )
    
    generating_questions: bool = Field(
        default=True,
        description="Enable HITL for question generation node"
    )
    
    def is_enabled_for_node(self, node_name: str) -> bool:
        """
        Check if HITL is enabled for a specific node
        
        Args:
            node_name: Name of the node
            
        Returns:
            True if HITL is enabled for the node, False otherwise
        """
        return getattr(self, node_name, False)
    
    @classmethod
    def all_enabled(cls) -> "HITLConfig":
        """Returns configuration with all flags enabled"""
        return cls(edit_material=True, generating_questions=True)
    
    @classmethod
    def all_disabled(cls) -> "HITLConfig":
        """Returns configuration with all flags disabled"""
        return cls(edit_material=False, generating_questions=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HITLConfig":
        """Create from dictionary"""
        return cls(**data)