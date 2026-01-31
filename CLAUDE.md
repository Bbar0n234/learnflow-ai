# CLAUDE.md

Instructions for Claude Code when working with this repository.

## Project Overview

LearnFlowAI v2 — clean rewrite using AI-Driven Development (AIDD) methodology.

**Status:** Documentation phase. Code implementation not started yet.

## Documentation Structure

All documentation is in `doc/`:

```
doc/
├── idea.md                    # What and why
├── vision.md                  # Technical vision, stack, architecture
│
├── product/                   # Product documentation
│   ├── use-cases.md
│   └── backlog.md
│
├── tech/                      # Technical documentation
│   ├── adr/                   # Architecture Decision Records
│   ├── architecture/          # Diagrams, component descriptions
│   ├── backend/
│   ├── frontend/
│   └── agent/
│
└── tasks/                     # Task management
    ├── tasklist-mvp.md
    └── iterations/
```

## Development Methodology

This project follows **AI-Driven Development (AIDD)**:

1. Developer = architect/CTO, defines contracts and architecture
2. LLM agent = executor, implements based on prepared context
3. Documentation first — all decisions documented before implementation
4. Context First — quality of output depends on quality of input context

## Current Phase

**Documentation transfer** — migrating product and technical decisions from Obsidian notes to project documentation.

## Guidelines

- Do NOT write code until documentation is complete and approved
- All architectural decisions must be documented as ADRs
- Use Russian for documentation content (English for code and technical terms)
