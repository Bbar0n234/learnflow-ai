# ADR-001: Architecture Overview

## Status
Accepted

## Context
LearnFlow AI requires a robust, scalable architecture that can handle complex LLM workflows while maintaining security, observability, and extensibility. The system needs to process various input types (text, images), orchestrate multiple LLM calls, and provide real-time feedback to users.

## Decision

### Core Architecture: LangGraph-based Workflow Engine

We chose LangGraph as our workflow orchestration framework for the following reasons:

1. **State Management** - Built-in support for complex state transitions and accumulation
2. **Graph-based Flow** - Visual representation of processing pipeline
3. **HITL Support** - Native human-in-the-loop capabilities
4. **Checkpointing** - Ability to pause, resume, and rollback workflows
5. **Streaming** - Real-time updates as processing occurs

### Layered Architecture

```
┌─────────────────────────────────────────┐
│           Presentation Layer            │
│    (Web UI, Telegram Bot, REST API)    │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│          Application Layer              │
│   (Workflow Orchestration, Business     │
│          Logic, HITL Manager)           │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│           Domain Layer                  │
│    (Nodes, State Models, Prompts)      │
└─────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────┐
│        Infrastructure Layer             │
│  (LLM Providers, Storage, Monitoring)   │
└─────────────────────────────────────────┘
```

### Node Architecture

All workflow nodes extend `BaseWorkflowNode` which provides:

```python
class BaseWorkflowNode(ABC):
    def __init__(self):
        self.logger = self._setup_logger()
        self.tracer = self._setup_tracer()
    
    @abstractmethod
    async def validate_input_state(self, state: ExamState) -> bool:
        """Validate state before processing"""
        pass
    
    @abstractmethod
    async def process(self, state: ExamState) -> ExamState:
        """Main processing logic"""
        pass
    
    async def __call__(self, state: ExamState) -> ExamState:
        """Orchestrate validation, processing, and error handling"""
        if not await self.validate_input_state(state):
            raise InvalidStateError()
        
        try:
            return await self.process(state)
        except Exception as e:
            self.logger.error(f"Node processing failed: {e}")
            return self._handle_error(state, e)
```

Benefits:
- Consistent error handling
- Automatic tracing and logging
- State validation
- Testability through dependency injection

### State Management

Using Pydantic models with LangGraph annotations:

```python
class ExamState(BaseModel):
    thread_id: str
    exam_question: str
    generated_content: Annotated[str, accumulate]
    recognized_text: Annotated[List[str], accumulate]
    synthesized_material: str
    gap_questions: Annotated[List[Question], accumulate]
    answers: Annotated[List[Answer], accumulate]
    hitl_feedback: Optional[HITLFeedback]
```

### LLM Provider Abstraction

Support for multiple providers through adapter pattern:

```python
class LLMProvider(Protocol):
    async def generate(self, prompt: str, **kwargs) -> str: ...
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]: ...

class OpenAIProvider(LLMProvider): ...
class OllamaProvider(LLMProvider): ...
class CustomProvider(LLMProvider): ...
```

## Consequences

### Positive
- **Modularity** - Easy to add/modify nodes without affecting others
- **Testability** - Each node can be tested in isolation
- **Observability** - Built-in tracing at every layer
- **Flexibility** - Support for any OpenAI-compatible LLM
- **Scalability** - Nodes can be distributed if needed
- **Maintainability** - Clear separation of concerns

### Negative
- **Complexity** - Learning curve for LangGraph
- **Overhead** - Additional abstraction layers
- **Dependencies** - Tied to LangGraph ecosystem

### Neutral
- **Performance** - Trade-off between flexibility and raw speed
- **Resource Usage** - State management requires memory

## Implementation Notes

1. All nodes must extend `BaseWorkflowNode`
2. State modifications must use proper annotations
3. Error handling should be graceful with fallbacks
4. Tracing must be enabled for production debugging
5. Configuration through environment variables or YAML

## References
- [LangGraph Documentation](https://github.com/langchain-ai/langgraph)
- [Clean Architecture by Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)