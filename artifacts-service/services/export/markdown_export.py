"""Markdown exporter for documents."""

import zipfile
from pathlib import Path
from io import BytesIO
from typing import List

from .base import ExportEngine
from models import ExportFormat, PackageType


class MarkdownExporter(ExportEngine):
    """Export documents in Markdown format."""
    
    async def export_single_document(
        self,
        thread_id: str,
        session_id: str,
        document_name: str,
        format: ExportFormat = ExportFormat.MARKDOWN
    ) -> bytes:
        """Export a single Markdown document.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            document_name: Name of the document to export
            format: Export format (should be MARKDOWN)
            
        Returns:
            Document content as bytes
        """
        doc_path = self.get_document_path(thread_id, session_id, document_name)
        
        if not doc_path.exists():
            raise FileNotFoundError(f"Document not found: {document_name}")
        
        return doc_path.read_bytes()
    
    async def export_package(
        self,
        thread_id: str,
        session_id: str,
        package_type: PackageType,
        format: ExportFormat = ExportFormat.MARKDOWN
    ) -> bytes:
        """Export a package of Markdown documents as ZIP.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            package_type: Type of package (final or all)
            format: Export format (should be MARKDOWN)
            
        Returns:
            ZIP archive as bytes
        """
        session_path = self.get_session_path(thread_id, session_id)
        
        if not session_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        
        documents = self.get_package_documents(session_path, package_type)
        
        if not documents:
            raise FileNotFoundError("No documents found for export")
        
        # Create ZIP archive in memory
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for doc_path in documents:
                # Determine archive name
                if "answers" in doc_path.parts:
                    # Preserve answers subdirectory structure
                    archive_name = f"answers/{doc_path.name}"
                else:
                    archive_name = doc_path.name
                
                # Add file to archive
                zipf.write(doc_path, archive_name)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    def merge_documents(self, documents: List[Path]) -> str:
        """Merge multiple Markdown documents into one.
        
        Args:
            documents: List of document paths
            
        Returns:
            Merged content as string
        """
        merged = []
        
        for doc_path in documents:
            if doc_path.exists():
                content = doc_path.read_text(encoding='utf-8')
                
                # Add document header
                doc_name = doc_path.stem.replace('_', ' ').title()
                merged.append(f"# {doc_name}\n\n")
                merged.append(content)
                merged.append("\n\n---\n\n")
        
        return "".join(merged).rstrip("---\n\n")