# CLAUDE.md

Instructions for Claude Code when working with this repository.

## Project Overview

LearnFlowAI v2 — clean rewrite using AI-Driven Development (AIDD) methodology.

**Status:** Documentation phase. Code implementation not started yet.

## Documentation Structure

All documentation is in `doc/`. Navigation and full structure — see [doc/index.md](doc/index.md).

<!-- TODO: актуализировать дерево структуры после завершения Phase B -->

## Development Methodology

This project follows **AI-Driven Development (AIDD)**:

1. Developer = architect/CTO, defines contracts and architecture
2. LLM agent = executor, implements based on prepared context
3. Documentation first — all decisions documented before implementation
4. Context First — quality of output depends on quality of input context

## Current Phase

**Phase B: Detailed Architecture** — designing modules, interfaces, contracts. Details: [doc/tasks/phase-b-architecture.md](doc/tasks/phase-b-architecture.md).

## Agent Boundaries

Agent does not make architectural decisions independently. Architecture, new components, interfaces, technology choices — only after explicit approval from the architect (user).

When a decision obviously and unambiguously follows from existing documentation — proceed without asking. When there is any doubt — ask first. The cost of an unnecessary question is low; the cost of an unauthorized architectural decision is high.

## Guidelines

- Do NOT write code until documentation is complete and approved
- All architectural decisions must be documented as ADRs
- Use Russian for documentation content (English for code and technical terms)
