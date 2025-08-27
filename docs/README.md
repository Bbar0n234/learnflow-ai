# Documentation Guide

Welcome to the LearnFlow AI documentation. This guide will help you navigate the documentation structure and find the information you need.

## Quick Start

- **New to LearnFlow AI?** → Start with [Overview](overview.md)
- **Want to deploy?** → See the root [README.md](../README.md#quick-start)
- **Need to understand the architecture?** → Check [ADR/001-architecture-overview.md](ADR/001-architecture-overview.md)
- **Want to contribute?** → Read [Development Conventions](conventions.md)

## Documentation Structure

### Core Documentation
- **[Overview](overview.md)** - Complete system architecture and technical details for developers
- **[Conventions](conventions.md)** - Development standards, coding guidelines, and project structure
- **[Business Model](business_model.md)** - Monetization strategy and business context

### Planning & Strategy
- **[Vision](planning/vision.md)** - Long-term project goals and direction
- **[Roadmap](planning/roadmap.md)** - Development timeline and milestones
- **[Insights](insights.md)** - AI-Driven Development philosophy and principles

### Architecture & Decisions
- **[ADR/](ADR/)** - Architecture Decision Records documenting key technical decisions
  - [001-architecture-overview.md](ADR/001-architecture-overview.md) - System architecture
  - [002-llm-guardrails.md](ADR/002-llm-guardrails.md) - Security implementation
  - [ADR-004-prompt-caching-strategy.md](ADR/ADR-004-prompt-caching-strategy.md) - Performance optimization

### Implementation & Development
- **[Backlog](backlog/)** - Current and archived implementation plans
  - [Index](backlog/index.md) - Overview of all initiatives
  - [Current](backlog/current/) - Active development items
  - [Archive](backlog/archive/) - Completed implementations
- **[Tech Debt](backlog/tech-debt/)** - Technical debt analysis and refactoring plans

### Research & Specifications
- **[Research](research/)** - Technical investigations and comparisons
- **[Specs](specs/)** - Detailed specifications for tools and technologies
- **[Architecture](architecture/)** - Architectural diagrams and NFR documentation

### Project Management
- **[Changelog](changelog.md)** - Version history and release notes
- **[Testing Strategy](TESTING_STRATEGY.md)** - Quality assurance approach

## Where to Go If You Need...

### Understanding the System
- **"What is LearnFlow AI?"** → [Overview](overview.md) and root [README.md](../README.md)
- **"How does it work technically?"** → [Architecture Overview](ADR/001-architecture-overview.md)
- **"What are the main components?"** → [Overview - System Architecture](overview.md#system-architecture)

### Getting Started
- **"How to install and run?"** → Root [README.md](../README.md#quick-start)
- **"How to develop locally?"** → [Conventions](conventions.md) and root [README.md](../README.md#development)
- **"What's the project structure?"** → [Conventions](conventions.md)

### Contributing & Development
- **"How to contribute?"** → [Conventions](conventions.md)
- **"What are the coding standards?"** → [Conventions](conventions.md)
- **"How to add new features?"** → [Backlog](backlog/) for current priorities

### Architecture & Technical Decisions
- **"Why was this technology chosen?"** → [ADR/](ADR/) directory
- **"How is security implemented?"** → [LLM Guardrails ADR](ADR/002-llm-guardrails.md)
- **"What's the system architecture?"** → [Architecture Overview ADR](ADR/001-architecture-overview.md)

### Business & Strategy
- **"What's the business model?"** → [Business Model](business_model.md)
- **"What's the long-term vision?"** → [Vision](planning/vision.md)
- **"What's being developed next?"** → [Roadmap](planning/roadmap.md)

### Troubleshooting & Support
- **"How to debug issues?"** → [Overview - Monitoring & Debugging](overview.md#monitoring-debugging)
- **"How to test the system?"** → [Testing Strategy](TESTING_STRATEGY.md)
- **"What are the current limitations?"** → [Overview - Technical Details](overview.md#technical-details)

## Documentation Maintenance

This documentation follows AI-Driven Development principles:
- **Living Documentation**: Core files are kept up-to-date with system changes
- **Decision Recording**: All architectural decisions are documented in ADRs
- **Implementation Tracking**: All features are planned, implemented, and archived with summaries

### Updating Documentation
- Always update [Overview](overview.md) when system architecture changes
- Create ADRs for significant technical decisions
- Document completed implementations in the backlog archive
- Keep the [Changelog](changelog.md) current with releases

For questions about the documentation or suggestions for improvements, please create an issue in the repository.