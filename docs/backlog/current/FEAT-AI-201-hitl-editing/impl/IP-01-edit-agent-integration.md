# Implementation Plan: Edit Agent Integration

## Overview

Minimal integration of an edit agent into LearnFlow AI workflow for MVP. The agent allows users to iteratively edit synthesized educational material through the existing Telegram bot interface. 

**Key principles:**
- Port working code from Jupyter notebook with minimal changes
- Reuse existing HITL patterns from recognition/questions nodes  
- No new infrastructure (no WebSocket, SSE, or complex versioning)
- 4-6 days implementation timeline
- Feature flag for easy enable/disable

## Architecture Design

### 1. Node Architecture

#### 1.1 New EditMaterialNode

**Location**: `learnflow/nodes/edit_material.py`

**Base Class**: Extends `BaseWorkflowNode` (using existing HITL pattern from recognition/questions nodes)

**Core Components**:
- Reuses `synthesized_material` from ExamState as document to edit
- Fuzzy text matching using `fuzzysearch` library (direct port from Jupyter notebook)
- Action-based workflow (edit, message, complete)
- Auto-save to LocalArtifactsManager after each edit

#### 1.2 Minimal State Extensions

**Modified State**: `learnflow/core/state.py`

Add only these fields to existing `ExamState`:

```python
# Minimal additions to ExamState
edit_count: int = Field(default=0, description="Total number of edits performed")
needs_user_input: bool = Field(default=True, description="Flag for HITL interaction")
agent_message: Optional[str] = Field(default=None, description="Message from edit agent to user")
last_action: Optional[str] = Field(default=None, description="Type of last action (edit/message/complete)")
```

**Important clarifications**:
- We reuse existing `feedback_messages` field for edit history tracking (already in state)
- We reuse existing `synthesized_material` field as the document to edit (no need for separate `document` field)
- This means we're adding exactly 4 new fields, not 6 as in the Jupyter notebook

### 2. Data Flow Integration

#### 2.1 Workflow Modification

**Current Flow**:
```
synthesis_material -> generating_questions
```

**New Flow (with optional edit)**:
```
synthesis_material -> edit_material -> generating_questions
```

**Skip condition**: If user doesn't want to edit, node immediately transitions to `generating_questions`

#### 2.2 Node Transitions

- `synthesis_material` sets `synthesized_material` in state
- `edit_material` works with `synthesized_material` directly (no document copying)
- Uses existing HITL pattern with `interrupt()` for user input
- On "complete" action or skip, updates `synthesized_material` and goes to `generating_questions`
- Each edit triggers auto-save via LocalArtifactsManager

### 3. Storage and Persistence

#### 3.1 Auto-save Mechanism

**Integration with LocalArtifactsManager**:
- After each successful edit, update the single document: `{session_path}/edited_material.md`
- Maintain lightweight edit history in JSON: `{session_path}/edit_history.json`
- Use existing `save_artifact()` method from LocalArtifactsManager

**Important**: Only the successfully matched delta (old_text/new_text pair) is sent to artifacts service via REST API, not the entire document. Fuzzy matching happens in the edit agent node before any API call.

**Edit history JSON structure** (minimal overhead):
```json
{
  "edits": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "edit_number": 1,
      "old_text_preview": "First 50 chars of replaced text...",
      "new_text_preview": "First 50 chars of new text...",
      "similarity": 0.95
    }
  ],
  "total_edits": 5,
  "last_modified": "2024-01-15T10:35:00Z"
}
```

#### 3.2 Simple REST API Approach

**No real-time needed for MVP**:
- Telegram bot polls for updates via existing REST endpoints
- Web UI (if added later) can poll `/document/{thread_id}` endpoint
- Each edit is immediately persisted, so clients always get latest version

### 4. Minimal File Changes

**New files (only 2)**:
```
learnflow/
├── nodes/
│   └── edit_material.py         # New edit node (ports logic from Jupyter)
└── utils/
    └── fuzzy_matcher.py         # Fuzzy matching function from notebook
```

**Modified files (3)**:
```
learnflow/
├── core/
│   ├── state.py                 # Add 4 fields to ExamState
│   └── graph.py                 # Add edit_material node to workflow
└── nodes/
    └── __init__.py              # Export EditMaterialNode
```

**Optional API additions** (can be added later if needed):
```
learnflow/api/
└── main.py                      # Add 2 simple endpoints for manual edit control
```

### 5. API Endpoints (Optional for MVP)

**Note**: The edit node works through LangGraph's HITL mechanism. These endpoints are optional for external control.

#### 5.1 Minimal REST Endpoints

**GET** `/document/{thread_id}`
- Returns current `synthesized_material` from state
- Response: `{"document": "...", "edit_count": 0, "status": "editing|completed"}`

**POST** `/edit/{thread_id}/patch` 
- Apply a validated edit patch (after successful fuzzy matching in agent node)
- Request body: 
```json
{
  "old_text": "exact text that was found and validated",
  "new_text": "replacement text",
  "edit_metadata": {
    "similarity": 0.95,
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```
- Response: `{"success": true, "edit_count": 1, "document_updated": true}`

**Important flow**:
1. Agent node performs fuzzy matching locally (using logic from Jupyter notebook)
2. If successful match found, sends validated patch to artifacts service
3. Artifacts service applies simple replacement (no fuzzy logic needed)
4. If no match or poor similarity, agent logs error and retries with user feedback

Note: The fuzzy matching logic from `_experiments/notebooks/learnflow_edit_agent.ipynb` already handles uniqueness - it takes the first match from `fuzzysearch.find_near_matches()`

**Note**: Primary interaction happens through Telegram bot using existing workflow mechanisms.

### 6. Integration Points

#### 6.1 LocalArtifactsManager Integration

**Reuse existing methods**:
- Use `save_artifact()` to save after each edit: `save_artifact(session_path, f"edit_{edit_count}.md", document)`
- Final save: `save_artifact(session_path, "edited_material.md", final_document)`
- No new methods needed - existing functionality is sufficient

#### 6.2 Telegram Bot Integration

**Existing interaction flow**:
- Bot already handles HITL interrupts from other nodes (recognition, questions)
- Edit node will work the same way - interrupt for user input
- No changes needed to bot code

## Implementation Tasks (MVP - 4-6 days)

### Day 1-2: Setup and Core Logic

1. **Add dependency**
   - Run: `poetry add fuzzysearch`

2. **Port fuzzy matcher from notebook**
   - Create `learnflow/utils/fuzzy_matcher.py`
   - Copy `fuzzy_find_and_replace()` function from Jupyter
   - Add basic tests

3. **Extend ExamState**
   - Add 4 fields to `learnflow/core/state.py`:
     - `edit_count: int = 0`
     - `needs_user_input: bool = True`
     - `agent_message: Optional[str] = None`
     - `last_action: Optional[str] = None`

### Day 3-4: Create Edit Node

4. **Implement EditMaterialNode**
   - Create `learnflow/nodes/edit_material.py`
   - Port main logic from Jupyter's `main_node()` function
   - Adapt to use `synthesized_material` instead of separate document
   - Add auto-save using existing LocalArtifactsManager

5. **Define action models**
   - Add Pydantic models for ActionDecision, EditDetails, MessageDetails
   - Reuse from Jupyter notebook with minimal changes

### Day 5: Integration

6. **Wire into workflow**
   - Modify `learnflow/core/graph.py`:
     - Import EditMaterialNode
     - Add node: `workflow.add_node("edit_material", edit_node)`
     - Update flow: synthesis → edit_material → questions
   - Update `learnflow/nodes/__init__.py` to export EditMaterialNode

7. **Test with existing bot**
   - Run full workflow with Telegram bot
   - Verify HITL interrupts work
   - Check auto-save functionality

### Day 6: Polish and Optional API

8. **Add optional REST endpoints** (if time permits)
   - `GET /document/{thread_id}` - return current document
   - `POST /edit/{thread_id}` - manual edit trigger
   - Can be skipped for MVP since bot handles everything

9. **Basic testing**
   - Test fuzzy matching edge cases
   - Test workflow continuity
   - Test save/load of edited documents

## Testing Strategy (Simplified for MVP)

### Manual Testing Checklist

1. **Fuzzy Matching**:
   - Test with exact match
   - Test with minor typos (1-2 chars difference)
   - Test with whitespace differences
   - Test when text not found

2. **Edit Flow**:
   - Test edit -> continue editing -> edit -> complete
   - Test edit -> complete immediately
   - Test message -> user response -> edit
   - Test skip editing (go directly to questions)

3. **Integration**:
   - Full workflow through Telegram bot
   - Verify saves appear in artifacts folder
   - Check edited document is used for question generation

## Deployment (MVP)

### Configuration

**Add to `.env`**:
```bash
FUZZY_MATCH_THRESHOLD=0.85  # Similarity threshold for text matching
EDIT_AGENT_ENABLED=true      # Feature flag to enable/disable edit node
```

### Docker

**No changes needed** - fuzzysearch will be added via poetry, no new ports or volumes required.

### Rollback

If issues arise:
1. Set `EDIT_AGENT_ENABLED=false` in `.env`
2. Edit node will pass through without interaction
3. Workflow continues: synthesis -> questions (original flow)

## Known Limitations (MVP)

1. **Fuzzy matching**: May not find text with >15% differences
2. **No undo**: Edits are permanent (but versioned in artifacts)
3. **Single user**: No concurrent editing support
4. **Text only**: No formatting preservation (markdown is plain text)

## Future Enhancements (Post-MVP)

Once MVP is validated with users:
- Better fuzzy matching algorithms
- Undo/redo functionality  
- Batch edit operations
- Edit templates for common corrections
- Web UI with live preview

## Conclusion

This simplified implementation plan focuses on MVP delivery in 4-6 days by:
- Reusing existing HITL patterns and infrastructure
- Porting proven logic from the Jupyter notebook
- Minimal changes to existing codebase (2 new files, 3 modified files)
- No WebSocket/SSE complexity - just REST API and existing bot integration
- Feature flag for easy rollback if needed

The edit agent will allow users to iteratively refine synthesized educational materials through the Telegram bot interface, with each edit automatically saved to the artifacts storage for persistence and version tracking.