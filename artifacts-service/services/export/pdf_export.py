"""PDF exporter for documents."""

import zipfile
import markdown
from pathlib import Path
from io import BytesIO
from typing import List, Optional
import logging

from .base import ExportEngine
from ...models import ExportFormat, PackageType

logger = logging.getLogger(__name__)


class PDFExporter(ExportEngine):
    """Export documents in PDF format."""
    
    def __init__(self, base_path: Path):
        """Initialize PDF exporter.
        
        Args:
            base_path: Base path for data storage
        """
        super().__init__(base_path)
        self.weasyprint_available = self._check_weasyprint()
        
    def _check_weasyprint(self) -> bool:
        """Check if WeasyPrint is available."""
        try:
            import weasyprint
            return True
        except ImportError:
            logger.warning("WeasyPrint not available, using markdown2pdf fallback")
            return False
    
    async def export_single_document(
        self,
        thread_id: str,
        session_id: str,
        document_name: str,
        format: ExportFormat = ExportFormat.PDF
    ) -> bytes:
        """Export a single document as PDF.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            document_name: Name of the document to export
            format: Export format (should be PDF)
            
        Returns:
            PDF document as bytes
        """
        doc_path = self.get_document_path(thread_id, session_id, document_name)
        
        if not doc_path.exists():
            raise FileNotFoundError(f"Document not found: {document_name}")
        
        content = doc_path.read_text(encoding='utf-8')
        return await self.markdown_to_pdf(content, document_name)
    
    async def export_package(
        self,
        thread_id: str,
        session_id: str,
        package_type: PackageType,
        format: ExportFormat = ExportFormat.PDF
    ) -> bytes:
        """Export a package of documents as PDF ZIP.
        
        Args:
            thread_id: Thread identifier
            session_id: Session identifier
            package_type: Type of package (final or all)
            format: Export format (should be PDF)
            
        Returns:
            ZIP archive with PDFs as bytes
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
                # Convert to PDF
                content = doc_path.read_text(encoding='utf-8')
                pdf_content = await self.markdown_to_pdf(
                    content, 
                    doc_path.stem
                )
                
                # Determine archive name
                if "answers" in doc_path.parts:
                    archive_name = f"answers/{doc_path.stem}.pdf"
                else:
                    archive_name = f"{doc_path.stem}.pdf"
                
                # Add PDF to archive
                zipf.writestr(archive_name, pdf_content)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    async def markdown_to_pdf(
        self, 
        markdown_content: str, 
        title: Optional[str] = None
    ) -> bytes:
        """Convert Markdown content to PDF.
        
        Args:
            markdown_content: Markdown content
            title: Optional document title
            
        Returns:
            PDF content as bytes
        """
        if self.weasyprint_available:
            return await self._weasyprint_convert(markdown_content, title)
        else:
            return await self._fallback_convert(markdown_content, title)
    
    async def _weasyprint_convert(
        self, 
        markdown_content: str, 
        title: Optional[str] = None
    ) -> bytes:
        """Convert using WeasyPrint.
        
        Args:
            markdown_content: Markdown content
            title: Optional document title
            
        Returns:
            PDF content as bytes
        """
        import weasyprint
        
        # Convert Markdown to HTML
        html_content = markdown.markdown(
            markdown_content,
            extensions=['tables', 'fenced_code', 'codehilite', 'extra']
        )
        
        # Create complete HTML document with styling
        html = self._create_html_document(html_content, title)
        
        # Convert to PDF
        pdf_buffer = BytesIO()
        weasyprint.HTML(string=html).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        
        return pdf_buffer.getvalue()
    
    async def _fallback_convert(
        self, 
        markdown_content: str, 
        title: Optional[str] = None
    ) -> bytes:
        """Fallback conversion using markdown2pdf or similar.
        
        Args:
            markdown_content: Markdown content
            title: Optional document title
            
        Returns:
            PDF content as bytes
        """
        try:
            # Try using markdown2pdf if available
            import markdown2pdf
            pdf_buffer = BytesIO()
            markdown2pdf.convert(
                markdown_content,
                output=pdf_buffer,
                title=title
            )
            pdf_buffer.seek(0)
            return pdf_buffer.getvalue()
        except ImportError:
            # Last resort: return markdown as text in PDF-like format
            # This is a placeholder - in production, we'd want a proper fallback
            logger.error("No PDF conversion library available")
            raise RuntimeError(
                "PDF export requires WeasyPrint or markdown2pdf. "
                "Install with: pip install weasyprint"
            )
    
    def _create_html_document(
        self, 
        html_content: str, 
        title: Optional[str] = None
    ) -> str:
        """Create complete HTML document with styling.
        
        Args:
            html_content: HTML content
            title: Optional document title
            
        Returns:
            Complete HTML document
        """
        css_path = Path(__file__).parent / "templates" / "styles.css"
        
        # Default CSS if file doesn't exist
        if css_path.exists():
            css = css_path.read_text(encoding='utf-8')
        else:
            css = self._get_default_css()
        
        doc_title = title or "LearnFlow AI Export"
        
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_title}</title>
    <style>
    {css}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
    </div>
</body>
</html>
"""
    
    def _get_default_css(self) -> str:
        """Get default CSS for PDF export."""
        return """
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
}

h1, h2, h3, h4, h5, h6 {
    color: #2c3e50;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}

h1 {
    font-size: 2em;
    border-bottom: 2px solid #3498db;
    padding-bottom: 0.3em;
}

h2 {
    font-size: 1.5em;
}

h3 {
    font-size: 1.2em;
}

code {
    background-color: #f4f4f4;
    padding: 2px 4px;
    border-radius: 3px;
    font-family: 'Courier New', Courier, monospace;
}

pre {
    background-color: #f4f4f4;
    padding: 10px;
    border-radius: 5px;
    overflow-x: auto;
}

pre code {
    background-color: transparent;
    padding: 0;
}

blockquote {
    border-left: 4px solid #3498db;
    padding-left: 15px;
    color: #666;
    font-style: italic;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}

table th,
table td {
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}

table th {
    background-color: #f2f2f2;
    font-weight: bold;
}

table tr:nth-child(even) {
    background-color: #f9f9f9;
}

ul, ol {
    margin: 1em 0;
    padding-left: 30px;
}

li {
    margin: 0.5em 0;
}

a {
    color: #3498db;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 2em 0;
}

.page-break {
    page-break-after: always;
}

@media print {
    body {
        font-size: 11pt;
    }
    
    h1 {
        font-size: 18pt;
    }
    
    h2 {
        font-size: 14pt;
    }
    
    h3 {
        font-size: 12pt;
    }
}
"""