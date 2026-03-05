# CLAUDE.md

Instructions for Claude Code when working with this repository.

## Project Overview

LearnFlowAI v2 — clean rewrite using AI-Driven Development (AIDD) methodology.

**Status:** Architecture complete. Implementation phase.

## Documentation Structure

All documentation is in `doc/`. Navigation and full structure — see [doc/index.md](doc/index.md).

```
doc/
├── idea.md              # Что и зачем
├── vision.md            # Техническое видение, стек, архитектура
├── index.md             # Навигация по документации
│
├── product/             # use-cases, roadmap
├── tech/                # backend, frontend, conventions
│   └── adr/             # Architecture Decision Records
├── security/            # Модель угроз
└── tasks/               # Задачи и итерации
```

## Development Methodology

This project follows **AI-Driven Development (AIDD)**:

1. Developer = architect/CTO, defines contracts and architecture
2. LLM agent = executor, implements based on prepared context
3. Documentation first — all decisions documented before implementation
4. Context First — quality of output depends on quality of input context

## Current Phase

**Implementation** — architecture and documentation complete, moving to task decomposition and iterative development.

## Agent Boundaries

Agent does not make architectural decisions independently. Architecture, new components, interfaces, technology choices — only after explicit approval from the architect (user).

When a decision obviously and unambiguously follows from existing documentation — proceed without asking. When there is any doubt — ask first. The cost of an unnecessary question is low; the cost of an unauthorized architectural decision is high.

## Guidelines

- All architectural decisions must be documented as ADRs
- Use Russian for documentation content (English for code and technical terms)
- Follow conventions from [doc/tech/conventions.md](doc/tech/conventions.md)
