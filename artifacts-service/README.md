# Artifacts Service

File storage and export service for LearnFlow AI artifacts with REST API, supporting PDF and Markdown export functionality.

## Overview

The Artifacts Service provides a comprehensive file storage and export system with thread-based organization for LearnFlow AI workflow outputs. It stores generated materials, recognized notes, synthesized content, gap analysis questions/answers, and provides export functionality to PDF and Markdown formats.

## File Structure

```
data/artifacts/
  {thread_id}/              # User ID from Telegram
    metadata.json           # Thread metadata
    sessions/
      {session_id}/         # UUID for each exam question
        session_metadata.json
        generated_material.md
        recognized_notes.md
        synthesized_material.md
        questions.md
        answers/
          question_1.md
          question_2.md
      {session_id_2}/
        ...
  {thread_id_2}/
    ...
```

## API Endpoints

### Health Check
- **GET /health** - Service health check

### Thread Management
- **GET /threads** - List all threads
- **GET /threads/{thread_id}** - Get thread information and sessions
- **DELETE /threads/{thread_id}** - Delete entire thread

### Session Management
- **GET /threads/{thread_id}/sessions/{session_id}** - List files in session
- **DELETE /threads/{thread_id}/sessions/{session_id}** - Delete session

### File Operations
- **GET /threads/{thread_id}/sessions/{session_id}/{path:path}** - Get file content
- **POST /threads/{thread_id}/sessions/{session_id}/{path:path}** - Create/update file
- **DELETE /threads/{thread_id}/sessions/{session_id}/{path:path}** - Delete file

### Export Operations
- **POST /export/pdf/{thread_id}/{session_id}** - Export session materials to PDF
- **POST /export/markdown/{thread_id}/{session_id}** - Export session materials to Markdown
- **GET /export/templates** - List available export templates
- **POST /export/custom** - Export with custom template and settings

## Configuration

Environment variables:

```bash
ARTIFACTS_HOST=0.0.0.0
ARTIFACTS_PORT=8001
ARTIFACTS_DATA_PATH=./data/artifacts
ARTIFACTS_MAX_FILE_SIZE=10485760      # 10MB
ARTIFACTS_MAX_FILES_PER_THREAD=100

# Export Configuration
EXPORT_PDF_ENGINE=weasyprint           # PDF generation engine
EXPORT_TEMPLATE_PATH=./templates       # Custom templates directory
EXPORT_CACHE_TTL=3600                  # Export cache time-to-live
EXPORT_MAX_SIZE=52428800               # 50MB max export size
```

## Running

### Standalone
```bash
cd artifacts-service
python -m app.main
```

### With Docker
```bash
docker-compose up artifacts-service
```

The service will be available at `http://localhost:8001`.

## Testing

### Health Check
```bash
curl http://localhost:8001/health
```

### Create a File
```bash
curl -X POST http://localhost:8001/threads/12345/sessions/uuid-123/test.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# Test Content\n\nHello world!", "content_type": "text/markdown"}'
```

### Read a File
```bash
curl http://localhost:8001/threads/12345/sessions/uuid-123/test.md
```

### List Threads
```bash
curl http://localhost:8001/threads
```

### Export to PDF
```bash
curl -X POST http://localhost:8001/export/pdf/12345/uuid-123 \
  -H "Content-Type: application/json" \
  -d '{
    "include_materials": true,
    "include_questions": true,
    "include_answers": true,
    "template": "academic",
    "settings": {
      "page_size": "A4",
      "font_size": 12,
      "margins": "normal"
    }
  }' \
  --output study_materials.pdf
```

### Export to Markdown
```bash
curl -X POST http://localhost:8001/export/markdown/12345/uuid-123 \
  -H "Content-Type: application/json" \
  -d '{
    "include_materials": true,
    "include_questions": true,
    "include_answers": true,
    "format": "github",
    "include_toc": true
  }' \
  --output study_materials.md
```

### List Export Templates
```bash
curl http://localhost:8001/export/templates
```

## Export Features

### PDF Export
- **Multiple Templates**: Academic, professional, minimalist styles
- **Customizable Layout**: Page size, margins, fonts, colors
- **Rich Content**: LaTeX math rendering, syntax highlighting, diagrams
- **Metadata**: Title pages, table of contents, headers/footers
- **Quality Control**: Vector graphics, embedded fonts, print-ready

### Markdown Export
- **Format Options**: GitHub, GitLab, standard Markdown flavors
- **Structure**: Automatic heading hierarchy and table of contents
- **Cross-references**: Internal links between sections
- **Code Blocks**: Syntax highlighting preservation
- **Math Notation**: LaTeX math expressions

### Export Templates
```
templates/
├── pdf/
│   ├── academic.html        # University-style template
│   ├── professional.html    # Business/corporate style
│   └── minimalist.html      # Clean, simple design
├── markdown/
│   ├── github.md           # GitHub-flavored markdown
│   ├── gitlab.md           # GitLab-flavored markdown
│   └── standard.md         # CommonMark standard
└── css/
    ├── academic.css        # Academic styling
    ├── professional.css    # Professional styling
    └── minimalist.css      # Minimal styling
```

### Bot Integration
The service integrates with the Telegram bot through:
- **Export Commands**: `/export` and `/export_menu` bot commands
- **Session Management**: Automatic session detection and material organization
- **Progress Updates**: Real-time export progress notifications
- **File Delivery**: Direct download links or file uploads to Telegram

```python
# Bot integration example
async def export_session_materials(thread_id: str, session_id: str, format: str):
    export_request = {
        "include_materials": True,
        "include_questions": True,
        "include_answers": True,
        "template": "academic" if format == "pdf" else "github"
    }
    
    response = await artifacts_client.export(
        thread_id=thread_id,
        session_id=session_id,
        format=format,
        options=export_request
    )
    
    return response.download_url
```

## Security Features

- Path traversal protection
- File size limits
- Content type validation
- Sanitized file paths
- Thread/session ID validation
- Export size and time limits
- Template injection prevention
- Safe PDF generation with sandboxing

## Supported Content Types

### Storage Content Types
- text/markdown
- application/json  
- text/plain

### Export Content Types
- application/pdf (PDF exports)
- text/markdown (Markdown exports)
- application/zip (Multi-file exports)
- text/html (HTML preview)