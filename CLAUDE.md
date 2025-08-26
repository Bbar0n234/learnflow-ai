# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LearnFlow AI is a universal LangGraph-based educational content generation system for any subject area and education level. It processes exam questions and handwritten note images to generate comprehensive study materials with gap analysis questions and answers. The system consists of:

- **FastAPI service** (`learnflow/`) - REST API for processing exam materials
- **Telegram bot** (`bot/`) - User interface for interacting with the system
- **LangGraph workflow** - Multi-node processing pipeline with HITL (Human-in-the-Loop) capabilities
- **Image recognition module** - OCR and handwritten text recognition for student notes
- **GitHub integration** - Automatic artifact storage and sharing
- **Prompt Configuration Service** (`prompt-config-service/`) - Dynamic personalized prompt generation service

## Development Commands

### Environment Setup
```bash
# Copy and configure environment variables
cp env.example .env
# Edit .env with your API keys

# Install dependencies using UV workspace
# Install all packages and groups
uv sync

# Install specific packages
uv sync --package learnflow  # Only learnflow service dependencies
uv sync --package bot        # Only bot service dependencies

# Install with specific groups
uv sync --group dev          # Development tools (ruff, mypy, etc.)
uv sync --group test         # Testing dependencies (pytest, etc.)
uv sync --group dev --group test  # Multiple groups

# Install specific package with specific group
uv sync --package learnflow --group dev   # Dev tools for learnflow only
uv sync --package bot --group test        # Test deps for bot only

# Quick startup script (starts both FastAPI service and Telegram bot)
./run.sh
```

### Running Services

#### FastAPI Service Only
```bash
uv run --package learnflow python -m learnflow.main
# Service available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

#### Telegram Bot Only
```bash
uv run --package bot python -m bot.main
```

**Available Bot Commands:**
- `/start` - Welcome message and instructions
- `/help` - Show available commands and usage
- `/hitl` - Configure Human-in-the-Loop settings (autonomous vs. guided modes)
- `/configure` - Configure prompt personalization settings (profiles, placeholders)
- `/reset_prompts` - Reset prompt settings to defaults
- `/reset` - Reset current session
- `/status` - Show current processing status

#### Docker Compose (Full Stack with LangFuse)
```bash
docker-compose up
# Includes: FastAPI, Bot, Prompt Config Service, LangFuse, PostgreSQL, Redis, ClickHouse, MinIO
```

#### Prompt Configuration Service Only
```bash
uv run --package prompt-config-service python -m main
# Service available at http://localhost:8002
# API docs at http://localhost:8002/docs
```

### Development Tools
```bash
# Health check
curl http://localhost:8000/health

# HITL Configuration API
curl http://localhost:8000/api/hitl/{user_id}                    # Get current HITL settings
curl -X POST http://localhost:8000/api/hitl/{user_id}/bulk      # Enable/disable all nodes
curl -X PATCH http://localhost:8000/api/hitl/{user_id}/node/edit_material  # Toggle specific node

# View logs
tail -f learnflow.log
```

## Architecture

### Core Components

#### LangGraph Workflow Pipeline
The system uses a multi-node workflow defined in `learnflow/graph.py`:

1. **input_processing** - Analyzes user input and determines processing path
2. **generating_content** - Generates comprehensive study material from exam questions
3. **recognition_handwritten** - OCR processing of handwritten notes with HITL refinement
4. **synthesis_material** - Combines generated content with recognized notes
5. **generating_questions** - Creates gap analysis questions with HITL review
6. **answer_question** - Generates detailed answers for gap questions

#### State Management
- **ExamState** (`learnflow/state.py`) - Typed state model for workflow data
- Supports image paths, recognized text, synthesized materials, and HITL feedback
- Uses Pydantic for validation and LangGraph annotations for accumulation

#### Node Architecture
All processing nodes extend `BaseWorkflowNode` (`learnflow/nodes/base.py`):
- Structured logging with trace IDs
- Error handling and state validation
- LangFuse integration for observability
- HITL interaction patterns

### Key Modules

#### Image Processing (`learnflow/file_utils.py`)
- Thread-based temporary storage for uploaded images
- Image validation (size, format, content type)
- Cleanup utilities for temporary files

#### GitHub Integration (`learnflow/github.py`)
- Automatic artifact storage in specified repository
- Branch and path management
- Markdown file creation and updates

#### Settings (`learnflow/settings.py`)
- Pydantic-based configuration management
- Environment variable loading with validation
- Service-specific settings (file limits, ports, etc.)

#### HITL Management (`learnflow/services/hitl_manager.py`)
- Configurable Human-in-the-Loop interaction control
- Per-user settings for autonomous vs. guided processing modes
- In-memory storage with thread-ID based configuration
- REST API endpoints for runtime configuration changes

#### Prompt Configuration Integration (`learnflow/services/prompt_client.py`)
- HTTP client for Prompt Configuration Service
- Retry mechanism with exponential backoff (3 attempts)
- Dynamic personalized prompt generation
- WorkflowExecutionError on service unavailability (no fallback)
- Context building from workflow state with proper field mapping

### Configuration Files

#### Prompts (`configs/prompts.yaml`)
Contains all system prompts for different workflow nodes:
- `generating_content_system_prompt` - Comprehensive material generation
- `recognition_system_prompt` - Handwritten notes processing
- `synthesize_system_prompt` - Content synthesis logic
- `gen_question_system_prompt` - Gap question generation
- `gen_answer_system_prompt` - Answer generation

#### Environment Variables (`.env`)
Required API keys and configuration:
- `OPENAI_API_KEY` - Primary LLM provider
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` - Observability
- `TELEGRAM_TOKEN` - Bot integration
- `GITHUB_TOKEN` - Repository access for artifacts
- `PROMPT_SERVICE_URL` - URL for Prompt Configuration Service (default: http://localhost:8002)
- `PROMPT_SERVICE_TIMEOUT` - Service timeout in seconds (default: 5)
- `PROMPT_SERVICE_RETRY_COUNT` - Number of retry attempts (default: 3)
- Database and service configuration

## Development Guidelines

### Working with LangGraph Nodes
- Extend `BaseWorkflowNode` for consistent behavior
- Implement proper state validation in `validate_input_state()`
- Handle HITL interactions through `Command` objects

### API Development
- FastAPI endpoints are in `learnflow/main.py`
- Use Pydantic models for request/response validation
- Implement proper error handling with meaningful HTTP status codes
- Thread-based processing for concurrent requests

### Testing Images
Sample images for recognition testing are in `images/`:
- `raw/` - Original handwritten notes
- `clipped/` - Processed/cropped versions

### Deployment
- Production deployment uses Docker Compose with full LangFuse stack
- Health checks available at `/health` endpoint
- Logs are structured with timestamp and trace ID correlation

## Troubleshooting

### Common Issues
- **Port conflicts**: Check if 8000 (FastAPI) or 3000 (LangFuse) are occupied
- **API key errors**: Verify all required keys are set in `.env`
- **UV dependencies**: Run `uv sync --upgrade` to update dependencies or `uv sync` to reinstall if conflicts occur
- **Docker volumes**: Use `docker-compose down -v` to reset persistent data

### Debugging
- Enable DEBUG logging via `LOG_LEVEL=DEBUG` in `.env`
- LangFuse tracing provides detailed workflow execution logs
- FastAPI has automatic interactive docs at `/docs` endpoint