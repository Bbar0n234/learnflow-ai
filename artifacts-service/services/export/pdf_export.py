"""PDF exporter for documents."""

import zipfile
import markdown
from pathlib import Path
from io import BytesIO
from typing import Optional
import logging
import pdfkit
import re

from .base import ExportEngine
from models import ExportFormat, PackageType

logger = logging.getLogger(__name__)


class PDFExporter(ExportEngine):
    """Export documents in PDF format."""
    
    def __init__(self, base_path: Path):
        """Initialize PDF exporter.
        
        Args:
            base_path: Base path for data storage
        """
        super().__init__(base_path)
    
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

    def add_blank_lines_before_lists(self, text: str) -> str:
        """
        Вставляет пустую строку перед каждым списком (нумерованным и ненумерованным) в Markdown-тексте,
        если перед списком нет уже пустой строки. Код-блоки (```...```) не изменяются.
        """
        LIST_RE = re.compile(r"""^              # начало строки
                                \s*            # необязательные пробелы / отступ
                                (?:> ?)?       # допускаем блок-цитаты >
                                (?:[-*+]       # маркеры маркированного списка
                                |\d+[.)])    # или цифра + точка/скобка
                                \s+            # обязательный пробел после маркера
                            """, re.VERBOSE)

        def is_list_line(line: str) -> bool:
            return bool(LIST_RE.match(line))

        parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        for idx, part in enumerate(parts):
            # обрабатываем только обычный текст (чётные индексы)
            if idx % 2 == 0:
                lines = part.splitlines()
                out: list[str] = []
                for i, line in enumerate(lines):
                    if is_list_line(line):
                        prev = lines[i - 1] if i else ""
                        # вставляем перенос, если его нет
                        if prev.strip() and not is_list_line(prev):
                            out.append("")
                    out.append(line)
                parts[idx] = "\n".join(out)
        return "".join(parts)
    
    async def markdown_to_pdf(
        self, 
        markdown_content: str, 
        title: Optional[str] = None
    ) -> bytes:
        """Convert using pdfkit with MathJax.
        
        Args:
            markdown_content: Markdown content
            title: Optional document title
            
        Returns:
            PDF content as bytes
        """
        # Настройка markdown с математикой
        md = markdown.Markdown(
            extensions=['mdx_math'],
            extension_configs={
                'mdx_math': {
                    'enable_dollar_delimiter': True
                }
            }
        )
        
        # HTML шаблон с MathJax
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <script type="text/javascript" async
                src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-MML-AM_CHTML">
            </script>
            <script type="text/x-mathjax-config">
                MathJax.Hub.Config({{
                    tex2jax: {{
                        inlineMath: [['$','$'], ['\\\\(','\\\\)']],
                        displayMath: [['$$','$$'], ['\\\\[','\\\\]']],
                        processEscapes: true
                    }}
                }});
            </script>
        </head>
        <body>
            {content}
        </body>
        </html>
        """
        
        fixed_md = self.add_blank_lines_before_lists(markdown_content)
        html = md.convert(fixed_md)
        html_content = html_template.format(content=html)
        
        # Опции для pdfkit
        options = {
            'javascript-delay': 5000,  # Время для рендеринга MathJax
            'no-stop-slow-scripts': None,
            'debug-javascript': None
        }
        
        # Convert to PDF using pdfkit (returns bytes directly)
        pdf_bytes = pdfkit.from_string(html_content, False, options=options)
        
        return pdf_bytes