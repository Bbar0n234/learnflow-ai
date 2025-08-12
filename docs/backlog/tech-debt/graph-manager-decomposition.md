# GraphManager Decomposition - Technical Debt Analysis

## Problem Statement

The current `GraphManager` class violates the Single Responsibility Principle and has grown into a 580+ line "God Object" that handles:
- LangGraph workflow execution
- PostgreSQL database operations  
- LangFuse session management
- Artifacts storage and GitHub integration
- Thread lifecycle management

This creates maintenance challenges, testing difficulties, and tight coupling between unrelated concerns.

## Architecture Constraints

**Critical Discovery**: LangGraph execution requires **intimate integration** at runtime that prevents full separation:

```python
# This integration is INSEPARABLE:
async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
    graph = self.workflow.compile(checkpointer=saver)  # DB needed FOR compilation
    
    async for event in graph.astream(
        input_state, 
        cfg={
            "callbacks": [self.langfuse_handler],  # Callback needed FOR execution
            "configurable": {"thread_id": thread_id}
        }
    ):
```

**LangGraph.astream() requires all dependencies as execution arguments** - they cannot be "injected" beforehand.

## Proposed Decomposition Strategy

### Level 1: Infrastructure Services (CAN be separated)

```python
class PostgresCheckpointer:
    """Manages connection pool and DB setup"""
    async def ensure_setup(self) -> None
    async def get_saver(self) -> AsyncPostgresSaver
    
class LangFuseSessionManager:
    """Manages LangFuse sessions and metadata"""
    def create_execution_config(self, thread_id: str) -> Dict[str, Any]
    def get_or_create_session(self, thread_id: str) -> str
```

### Level 2: Core Workflow Executor (MUST remain integrated)

```python
class WorkflowExecutor:
    """Coordinates LangGraph execution with necessary dependencies"""
    
    def __init__(self, 
                 postgres_checkpointer: PostgresCheckpointer,
                 session_manager: LangFuseSessionManager,
                 artifacts_service: ArtifactsService):
        # Dependencies injected but used at runtime
    
    async def execute_workflow(self, thread_id: str, input_state: ExamState) -> ExecutionResult:
        cfg = self.sessions.create_execution_config(thread_id)
        
        # CRITICAL: saver must be in same context as astream
        async with self.postgres.get_saver() as saver:
            graph = self.workflow.compile(checkpointer=saver)
            async for event in graph.astream(input_state, cfg):
                await self._handle_workflow_event(thread_id, event)
```

### Level 3: Business Services (FULLY separable)

```python
class ArtifactsService:
    """Independent artifacts management"""
    async def save_learning_material(self, thread_id: str, material_data: Dict) -> ArtifactResult
    async def push_complete_materials(self, thread_id: str, all_materials: Dict) -> ArtifactResult
    
class StateQueryService:  
    """Independent state operations (not execution)"""
    async def get_thread_state(self, thread_id: str) -> Optional[ExamState]
    async def delete_thread_data(self, thread_id: str) -> None
```

## What Can and Cannot Be Separated

### ✅ CAN be separated:
- DB setup and initialization (PostgresCheckpointer)
- LangFuse session management (LangFuseSessionManager)
- Artifacts business logic (ArtifactsService) 
- Read-only state operations (StateQueryService)
- Workflow configuration preparation

### ❌ CANNOT be separated:
- Core execution loop `graph.astream()`
- Context management for `AsyncPostgresSaver`
- Event handling within workflow
- Integration logic between LangGraph components

## Implementation Plan

### Phase 1: Extract Infrastructure Services
- [ ] Create `PostgresCheckpointer` with connection pooling
- [ ] Create `LangFuseSessionManager` for session lifecycle
- [ ] Move artifacts logic to dedicated `ArtifactsService`
- [ ] Create `StateQueryService` for read-only operations

### Phase 2: Create Integrated Core
- [ ] Create `WorkflowExecutor` that uses infrastructure services
- [ ] Maintain LangGraph execution integrity
- [ ] Implement proper event handling delegation

### Phase 3: High-Level Coordination  
- [ ] Create `ExamWorkflowService` as public API
- [ ] Coordinate all services through dependency injection
- [ ] Maintain backward compatibility

## Expected Benefits

### Maintainability
- **Before**: 580+ line monolith handling everything
- **After**: 5 focused classes (~50-200 lines each)

### Testability  
- **Before**: Must mock DB, LangFuse, GitHub, filesystem simultaneously
- **After**: Test each service independently + integration tests for core

### Code Organization
```
# New structure:
PostgresCheckpointer     # ~50 lines: DB setup + connection management
LangFuseSessionManager   # ~80 lines: sessions + metadata  
ArtifactsService         # ~150 lines: files + GitHub push
StateQueryService        # ~60 lines: read-only operations
WorkflowExecutor         # ~200 lines: core LangGraph execution
ExamWorkflowService      # ~100 lines: service coordination
```

### Developer Experience
- **Onboarding**: Learn only relevant service for your task
- **Debugging**: Clear error localization by service
- **Changes**: Modify one service without affecting others
- **Code Review**: Focused PRs with minimal conflicts

## Risks and Mitigation

### Risk: Breaking LangGraph Integration
**Mitigation**: Keep WorkflowExecutor as integrated core, extensive integration testing

### Risk: Over-Engineering
**Mitigation**: Start with infrastructure extraction, avoid premature abstraction

### Risk: Performance Regression  
**Mitigation**: Implement connection pooling, benchmark against current implementation

## Success Metrics

- [ ] Code coverage >80% for each service
- [ ] Integration tests pass without mocking LangGraph dependencies
- [ ] Performance regression <10% 
- [ ] New developer onboarding time reduced by 50%
- [ ] Bug localization time improved (measured by issue resolution time)

## References

- Current implementation: `learnflow/core/graph_manager.py` (585 lines)
- LangGraph documentation on checkpointers and callbacks
- Clean Architecture principles (Uncle Bob)
- SOLID principles application to workflow orchestration