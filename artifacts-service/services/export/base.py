"""Base export engine for document export."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from models import ExportFormat, PackageType


class ExportEngine(ABC):
    """Base class for export engines."""
    
    def __init__(self, base_path: Path):
        """Initialize export engine.
        
        Args:
            base_path: Base path for data storage
        """
        self.base_path = base_path
    
    @abstractmethod
    async def export_single_document(
        self,
        thread_id: str,
        session_id: str,
        document_name: str,
        format: ExportFormat
    ) -> bytes:
        """Export a single document.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            document_name: Name of the document to export
            format: Export format
            
        Returns:
            Exported document as bytes
        """
        pass
    
    @abstractmethod
    async def export_package(
        self,
        thread_id: str,
        session_id: str,
        package_type: PackageType,
        format: ExportFormat
    ) -> bytes:
        """Export a package of documents.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            package_type: Type of package (final or all)
            format: Export format
            
        Returns:
            ZIP archive as bytes
        """
        pass
    
    def get_session_path(self, thread_id: str, session_id: str) -> Path:
        """Get path to session directory.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            
        Returns:
            Path to session directory
        """
        return self.base_path / thread_id / "sessions" / session_id
    
    def get_document_path(
        self, 
        thread_id: str, 
        session_id: str, 
        document_name: str
    ) -> Path:
        """Get path to specific document.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            document_name: Document name
            
        Returns:
            Path to document file
        """
        session_path = self.get_session_path(thread_id, session_id)
        
        # Handle special cases
        if document_name.startswith("answer_"):
            return session_path / "answers" / f"{document_name}.md"
        
        # Add .md extension if not present
        if not document_name.endswith(".md"):
            document_name = f"{document_name}.md"
            
        return session_path / document_name
    
    def get_package_documents(
        self, 
        session_path: Path, 
        package_type: PackageType
    ) -> List[Path]:
        """Get list of documents for package export.
        
        Args:
            session_path: Path to session directory
            package_type: Type of package
            
        Returns:
            List of document paths
        """
        documents = []
        
        # Final documents (always included)
        final_docs = [
            "synthesized_material.md",
            "questions.md"
        ]
        
        for doc in final_docs:
            doc_path = session_path / doc
            if doc_path.exists():
                documents.append(doc_path)
        
        # Add all answers
        answers_dir = session_path / "answers"
        if answers_dir.exists():
            documents.extend(sorted(answers_dir.glob("answer_*.md")))
        
        # Add intermediate documents if requested
        if package_type == PackageType.ALL:
            intermediate_docs = [
                "generated_material.md",
                "recognized_notes.md"
            ]
            for doc in intermediate_docs:
                doc_path = session_path / doc
                if doc_path.exists():
                    documents.append(doc_path)
        
        return documents
    
    def format_filename(
        self,
        base_name: str,
        session_id: str,
        extension: str
    ) -> str:
        """Format filename for export.
        
        Args:
            base_name: Base name of file
            session_id: Session identifier
            extension: File extension
            
        Returns:
            Formatted filename
        """
        # Extract timestamp from session_id if possible
        try:
            # Assuming session_id format: YYYYMMDD_HHMMSS
            timestamp = session_id
        except:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return f"{base_name}_{timestamp}.{extension}"