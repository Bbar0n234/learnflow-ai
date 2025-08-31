"""ZIP exporter for batch document export."""

import zipfile
from pathlib import Path
from io import BytesIO
from typing import List, Dict, Any

from .base import ExportEngine
from .markdown_export import MarkdownExporter
from .pdf_export import PDFExporter
from models import ExportFormat, PackageType


class ZIPExporter:
    """Export multiple documents as ZIP archive."""
    
    def __init__(self, base_path: Path):
        """Initialize ZIP exporter.
        
        Args:
            base_path: Base path for data storage
        """
        self.base_path = base_path
        self.markdown_exporter = MarkdownExporter(base_path)
        self.pdf_exporter = PDFExporter(base_path)
    
    async def export_session_archive(
        self,
        thread_id: str,
        session_id: str,
        package_type: PackageType,
        format: ExportFormat
    ) -> bytes:
        """Export session as ZIP archive.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            package_type: Type of package (final or all)
            format: Export format for documents in archive
            
        Returns:
            ZIP archive as bytes
        """
        # Select appropriate exporter
        if format == ExportFormat.PDF:
            exporter = self.pdf_exporter
        else:
            exporter = self.markdown_exporter
        
        # Use exporter's package method
        return await exporter.export_package(
            thread_id, 
            session_id, 
            package_type, 
            format
        )
    
    async def export_thread_archive(
        self,
        thread_id: str,
        format: ExportFormat,
        limit: int = 5
    ) -> bytes:
        """Export multiple sessions from a thread as ZIP.
        
        Args:
            thread_id: Thread identifier
            format: Export format for documents
            limit: Maximum number of sessions to include
            
        Returns:
            ZIP archive as bytes
        """
        thread_path = self.base_path / thread_id / "sessions"
        
        if not thread_path.exists():
            raise FileNotFoundError(f"Thread not found: {thread_id}")
        
        # Get session directories (sorted by creation time)
        session_dirs = sorted(
            [d for d in thread_path.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:limit]
        
        if not session_dirs:
            raise FileNotFoundError("No sessions found in thread")
        
        # Create ZIP archive in memory
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for session_dir in session_dirs:
                session_id = session_dir.name
                
                # Export each session
                try:
                    session_archive = await self.export_session_archive(
                        thread_id,
                        session_id,
                        PackageType.FINAL,  # Default to final documents
                        format
                    )
                    
                    # Add session archive to main archive
                    archive_name = f"session_{session_id}.zip"
                    zipf.writestr(archive_name, session_archive)
                    
                except Exception as e:
                    # Log error but continue with other sessions
                    print(f"Error exporting session {session_id}: {e}")
                    continue
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    async def export_custom_selection(
        self,
        selections: List[Dict[str, Any]],
        format: ExportFormat
    ) -> bytes:
        """Export custom selection of documents.
        
        Args:
            selections: List of document selections
                Each item should have: thread_id, session_id, document_names
            format: Export format
            
        Returns:
            ZIP archive as bytes
        """
        # Select appropriate exporter
        if format == ExportFormat.PDF:
            exporter = self.pdf_exporter
        else:
            exporter = self.markdown_exporter
        
        # Create ZIP archive in memory
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for selection in selections:
                thread_id = selection['thread_id']
                session_id = selection['session_id']
                document_names = selection.get('document_names', [])
                
                for doc_name in document_names:
                    try:
                        # Export individual document
                        content = await exporter.export_single_document(
                            thread_id,
                            session_id,
                            doc_name,
                            format
                        )
                        
                        # Determine file extension
                        ext = 'pdf' if format == ExportFormat.PDF else 'md'
                        
                        # Add to archive with proper path
                        archive_path = f"{session_id}/{doc_name}.{ext}"
                        zipf.writestr(archive_path, content)
                        
                    except Exception as e:
                        # Log error but continue
                        print(f"Error exporting {doc_name}: {e}")
                        continue
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()