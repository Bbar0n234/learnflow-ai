# Memory System Implementation Guide

**Status:** Design guide for post-MVP feature development  
**Audience:** Architects and engineers implementing multi-layer memory  
**Related:** `doc/research/agent-memory-architecture.md`

---

## 1. Core Design Decisions

### Decision 1: Memory Storage Backend

**Question:** Where do we store User Memory and Project Memory?

**Options:**
1. PostgreSQL + pgvector extension (single data store)
2. Redis (vectors + relational in one DB)
3. Separate vector DB (Pinecone, Weaviate) + PostgreSQL (relational)
4. Hybrid: PostgreSQL for long-term, Redis for short-term caching

**RECOMMENDATION: PostgreSQL + pgvector**

**Rationale:**
- Single data store eliminates distributed transaction complexity
- pgvector is mature, battle-tested (Supabase, etc.)
- Integrates with existing PostgreSQL infrastructure
- Supports full-text search + vector search in same query
- Simple backup/restore model
- ACID transactions ensure consistency
- Cost-effective: no separate vector DB infrastructure

**Consequences:**
- pgvector slower than specialized vector DBs for billion-scale (not relevant for MVP)
- Requires PostgreSQL 14+ (already deployed)

**Implementation:**
```sql
CREATE TABLE user_memories (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI/Claude embedding size
    memory_type VARCHAR(50),  -- 'semantic' | 'episodic'
    created_at TIMESTAMP DEFAULT NOW(),
    accessed_at TIMESTAMP DEFAULT NOW(),
    relevance_score FLOAT,  -- Updated during consolidation
    version INT DEFAULT 1,  -- For UPDATE operations
    UNIQUE(user_id, content(256))  -- Prevent duplicates
);

CREATE INDEX ON user_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);  -- Approximate NN search

CREATE TABLE project_memories (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),
    memory_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    accessed_at TIMESTAMP DEFAULT NOW(),
    relevance_score FLOAT,
    version INT DEFAULT 1,
    UNIQUE(project_id, content(256))
);

CREATE INDEX ON project_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

### Decision 2: Consolidation Frequency & Strategy

**Question:** How often should we consolidate memories? How aggressive with deduplication?

**Options:**
1. Per-turn consolidation (expensive, guarantees freshness)
2. Every N turns (batched, e.g., every 50 messages)
3. Nightly batch job (cheap, delayed consolidation)
4. Hybrid: per-turn dedup (fast similarity check) + nightly merge (slow consolidation)

**RECOMMENDATION: Hybrid approach**

**Rationale:**
- Per-turn dedup prevents obvious duplicates (fast, <50ms)
- Nightly consolidation merges subtle duplicates + summarizes (slow, acceptable off-hours)
- Balances freshness (user sees changes quickly) with cost (consolidation expensive)

**Implementation Timeline:**
```
Per-turn (immediate):
1. Generate embedding for new memory
2. Query: SELECT * FROM memories WHERE user_id = ? 
          ORDER BY embedding <-> new_embedding LIMIT 5
3. If max cosine similarity > 0.92: UPDATE instead of ADD
4. Else: ADD new memory

Nightly consolidation (00:00 UTC):
1. For each user:
   a. Find cluster of similar memories (similarity > 0.95)
   b. Generate LLM-based summary of cluster
   c. Merge into single canonical memory
   d. Keep link to original memories (version history)
   e. Compute new embedding for summary
2. For each project: same process
3. Update relevance scores based on recency + access frequency
4. Mark memories as consolidated (update version)
```

---

### Decision 3: User Transparency & Control

**Question:** How much visibility should users have over agent-written memories?

**Options:**
1. **Opaque:** Agent writes to memory; user never sees (maximum speed, minimum trust)
2. **View-only:** User can see memories but not edit (some transparency, limited control)
3. **Full control:** User sees, edits, deletes individual memories (maximum transparency, UX overhead)
4. **Hybrid:** Agent writes; user approves before memory persists (trust + autonomy trade-off)

**RECOMMENDATION: View-only + delete capability (with roadmap to full edit)**

**Rationale for MVP:**
- User can see what agent learned (trust, compliance)
- User can delete problematic memories (control, privacy)
- Agent doesn't ask permission for every memory (UX, speed)
- Roadmap: enable edit in Phase 2

**UI Components Needed:**

1. **Memory Explorer Page**
   - Searchable/filterable list of all User + Project memories
   - Columns: content, type (semantic/episodic), created_date, last_accessed, relevance_score
   - Delete button per memory
   - Export as JSON/CSV for audit

2. **Memory Status Widget** (chat page)
   - Show: "Agent learned 3 new facts from this conversation"
   - Link to Memory Explorer
   - Quick action: "Clear all project memories"

3. **Settings Page**
   - Toggle: "Agent-writable memory" (on/off per user)
   - Toggle: "Cross-project learning" (on/off, affects User Memory)
   - Retention policy: "Keep memories for X days/indefinite"
   - Sensitive categories TTL: "Delete health/finance memories after 30 days"

---

### Decision 4: Agent Autonomy Level

**Question:** When does the agent write to memory autonomously vs asking permission?

**Options:**
1. **Manual only:** User must explicitly request "Remember that..."
2. **Semi-autonomous:** Agent writes, shows user confirmation after (ask forgiveness)
3. **Full autonomous:** Agent writes without user knowledge
4. **Hybrid:** Different rules for semantic vs episodic

**RECOMMENDATION: Semi-autonomous with filtering**

**Rationale:**
- Explicit "Remember..." is nice but requires user engagement
- Full autonomous creates trust issues (how can user audit?)
- Semi-autonomous balances learning speed + transparency

**Rules for MVP:**

```
Memory Type: Semantic (facts, preferences)
├── Trigger: After user confirms/approves agent output
├── Content: Extract preference from confirmation
├── Pattern: "Based on your feedback, I learned you prefer..."
└── User sees: Post-chat summary "Agent learned: X"

Memory Type: Episodic (interactions, outcomes)
├── Trigger: After successful completed task
├── Content: Summarize interaction (what worked)
├── Pattern: "This approach succeeded because..."
└── User sees: Optional logging visible in chat

Memory Type: Consolidation (background)
├── Trigger: Nightly batch job
├── Content: No new information; merging existing
├── User sees: Nothing (consolidation is internal optimization)
```

**Explicit triggers (always ask):**
- Storing sensitive data (health, finance, contact info)
- Deleting or significant modification of existing memory
- Extracting personal opinion/assumption about user

---

### Decision 5: Memory Injection Strategy

**Question:** How much memory context do we inject into the LLM prompt?

**Options:**
1. **All memories:** Inject entire User + Project memory store (maximizes information, wastes tokens)
2. **Top-k retrieval:** Only inject most relevant N memories (balanced, standard)
3. **Selective by node:** Different nodes request different memory layers
4. **Adaptive:** Inject amount based on available token budget

**RECOMMENDATION: Top-k retrieval with node-level selection**

**Rationale:**
- Reduces token bloat from irrelevant memories
- Allows different nodes to use different memory types
- Prevents "cognitive paralysis" from too much context

**Implementation:**

```python
# In LangGraph node:
async def generate_outline(state, config) -> Command:
    # Get user/project memories relevant to current task
    user_memories = await retriever.search(
        query=state.input,  # Embed user query
        user_id=state.user_id,
        limit=3,  # Top-3 only
        min_similarity=0.7,  # Filter noise
        recency_weight=1.5  # Recent memories ranked higher
    )
    
    project_memories = await retriever.search(
        query=state.input,
        project_id=state.project_id,
        limit=3,
        min_similarity=0.7,
        recency_weight=1.5
    )
    
    # Format for injection (total budget: ~150 tokens)
    memory_context = format_memory_context(
        user_memories=user_memories,
        project_memories=project_memories,
        max_tokens=150
    )
    
    # Inject into system message (before conversation history)
    prompt = [
        SystemMessage(content=SYSTEM_PROMPT),
        SystemMessage(content=memory_context),  # Memory burst
        *state.messages  # Conversation history
    ]
    
    response = await llm.ainvoke(prompt)
    # ... rest of logic
```

---

### Decision 6: Scoping Model (Cross-Project Memory)

**Question:** Should User Memory apply to all projects, or stay siloed?

**Options:**
1. **Siloed:** User Memory per project (no cross-project learning)
2. **Global:** Single User Memory shared across all projects
3. **Filtered:** Global User Memory, but project-scoped filtering (only relevant facts injected)
4. **Hierarchical:** User Memory as foundation + Project Memory overrides (future hub-and-spoke)

**RECOMMENDATION: Global with recency filtering**

**Rationale:**
- User preferences (work style, content preferences) are truly cross-project
- Filtering by project topic prevents irrelevant facts
- Simplifies implementation: single User Memory table
- Enables future inheritance model

**Scoping Rules:**

```
User Memory:
├── Scope: ALL projects for this user
├── Examples: "Prefers detailed feedback", "Uses technical jargon", "Iterates 3+ times"
├── Injection: Only if project_id NOT in memory.project_exceptions
└── TTL: Indefinite (user can delete)

Project Memory:
├── Scope: SINGLE project only
├── Examples: "Talk about AI safety", "Audience: non-technical", "Prefers: visual slides"
├── Injection: Always (project-scoped)
└── TTL: Indefinite (user can delete)

Retrieval Filter:
├── For new project: exclude episodic memories from different projects
├── For ongoing project: include all User Memory + all Project Memory
└── Recency weight: memories from current project +50% boost in ranking
```

---

## 2. Operational Decisions

### Decision 7: Memory Decay & Deletion

**Question:** Should old memories automatically expire?

**Options:**
1. **Indefinite retention:** Memories kept forever
2. **Exponential decay:** Older memories ranked lower over time
3. **Hard TTL:** Delete memories after N days/months
4. **Soft TTL:** Archive to separate table (recoverable)

**RECOMMENDATION: Indefinite retention for Phase 1; soft TTL for Phase 2+**

**Rationale for Phase 1:**
- Simpler to implement (no background cleanup)
- Supports compliance (users can request deletion)
- Cost not prohibitive yet (memory table small)

**Phase 2+ Roadmap:**
```
Default TTL Policy:
├── Semantic (facts): Indefinite
├── Episodic (interactions): 12 months
├── Conversation history: 90 days (searchable), 12 months (archive)
└── Sensitive data (health/finance): 30 days (unless user extends)

Implementation:
├── Soft delete: archived_at timestamp, not hard DELETE
├── Recovery: users can request archived memories
├── Hard delete: 2-year archive, then permanent deletion
└── Audit trail: log all deletions with reason
```

---

### Decision 8: Embeddings Strategy

**Question:** Which embedding model for memory vectors?

**Options:**
1. **OpenAI text-embedding-3-small** (cheap, ~$0.02/M tokens)
2. **OpenAI text-embedding-3-large** (expensive, ~$0.13/M tokens)
3. **Open-source: nomic-embed-text** (free, self-hosted)
4. **Claude embeddings** (via Anthropic API)

**RECOMMENDATION: OpenAI text-embedding-3-small (Phase 1) → migrate to open-source (Phase 3)**

**Rationale:**
- Small model sufficient for agent memory use case (not semantic search across web)
- Cheap: ~$0.02/M tokens, 100 memories = ~$0.00001 cost
- Minimal migration pain if switching later
- Claude embeddings not yet widely available; prefer proven model

**Implementation:**

```python
from openai import AsyncOpenAI

async def embed_memory(content: str) -> list[float]:
    client = AsyncOpenAI(api_key=OPENAI_KEY)
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=content
    )
    return response.data[0].embedding  # 1536 dimensions

# In consolidation:
async def consolidate_memories(user_id: UUID):
    memories = await get_memories_for_consolidation(user_id)
    for cluster in memories:
        summary = await llm.summarize(cluster)
        new_embedding = await embed_memory(summary)
        await update_memory(cluster.id, summary, new_embedding)
```

---

### Decision 9: Retrieval Ranking Strategy

**Question:** How do we rank memories for relevance?

**Options:**
1. **Cosine similarity only:** Pure vector distance (simple, may miss temporal aspects)
2. **Hybrid:** Combine cosine similarity + BM25 (lexical search)
3. **Multi-factor:** Similarity + recency + access frequency + relevance_score
4. **Learning to rank:** Train ML model to predict which memories matter

**RECOMMENDATION: Multi-factor ranking (Phase 1) → Learning to rank (Phase 3)**

**Rationale:**
- Multi-factor captures most important signals: relevance (vector) + timeliness (recency) + importance (access frequency)
- Learning to rank premature before sufficient usage data

**Scoring Formula:**

```python
def rank_memory(memory, query_embedding, now):
    """
    Composite ranking score for memory retrieval
    """
    # 1. Semantic relevance (0-1)
    cosine_sim = cosine_similarity(memory.embedding, query_embedding)
    relevance = cosine_sim
    
    # 2. Recency boost (0-1.5)
    days_old = (now - memory.created_at).days
    if days_old < 7:
        recency = 1.5  # Recent memories prioritized
    elif days_old < 30:
        recency = 1.2
    elif days_old < 90:
        recency = 1.0
    else:
        recency = 0.8  # Older memories deprioritized
    
    # 3. Access frequency (0-1.3)
    if memory.accessed_count > 10:
        frequency = 1.3
    elif memory.accessed_count > 5:
        frequency = 1.1
    else:
        frequency = 1.0  # Rarely accessed memories neutral
    
    # 4. Consolidation status (0.9-1.0)
    if memory.consolidated:
        consolidation = 1.0
    else:
        consolidation = 0.95  # Slight boost to consolidated (dedup verified)
    
    # Final score: weighted combination
    final_score = (
        relevance * 0.5 +
        (recency - 1.0) * 0.2 +
        (frequency - 1.0) * 0.2 +
        (consolidation - 0.95) * 0.1
    )
    
    return final_score
```

---

## 3. Data Schema Reference

### user_memories Table

```sql
CREATE TABLE user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Content & type
    content TEXT NOT NULL,
    memory_type VARCHAR(50) NOT NULL CHECK (memory_type IN ('semantic', 'episodic')),
    
    -- Embedding & retrieval
    embedding vector(1536) NOT NULL,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(50) DEFAULT 'agent',  -- 'agent' or 'user'
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    accessed_count INT DEFAULT 0,
    relevance_score FLOAT DEFAULT 0.5,
    
    -- Versioning & consolidation
    version INT DEFAULT 1,
    consolidated BOOLEAN DEFAULT FALSE,
    consolidated_at TIMESTAMP,
    
    -- Lifecycle
    deleted_at TIMESTAMP,  -- Soft delete
    ttl_expires_at TIMESTAMP,  -- For automatic expiration
    
    UNIQUE(user_id, content(256)),  -- Prevent duplicate content
    CONSTRAINT content_not_empty CHECK (LENGTH(TRIM(content)) > 0)
);

CREATE INDEX idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_user_memories_created_at ON user_memories(created_at DESC);
CREATE INDEX idx_user_memories_type_user ON user_memories(memory_type, user_id);
```

### project_memories Table

```sql
CREATE TABLE project_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Content & type
    content TEXT NOT NULL,
    memory_type VARCHAR(50) NOT NULL CHECK (memory_type IN ('semantic', 'episodic')),
    
    -- Embedding & retrieval
    embedding vector(1536) NOT NULL,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(50) DEFAULT 'agent',
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    accessed_count INT DEFAULT 0,
    relevance_score FLOAT DEFAULT 0.5,
    
    -- Versioning & consolidation
    version INT DEFAULT 1,
    consolidated BOOLEAN DEFAULT FALSE,
    consolidated_at TIMESTAMP,
    
    -- Lifecycle
    deleted_at TIMESTAMP,
    ttl_expires_at TIMESTAMP,
    
    UNIQUE(project_id, content(256)),
    CONSTRAINT content_not_empty CHECK (LENGTH(TRIM(content)) > 0)
);

CREATE INDEX idx_project_memories_project_id ON project_memories(project_id);
CREATE INDEX idx_project_memories_embedding ON project_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_project_memories_created_at ON project_memories(created_at DESC);
```

### memory_audit_log Table (compliance)

```sql
CREATE TABLE memory_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_id UUID,  -- May be null if deleted memory
    operation VARCHAR(50) NOT NULL CHECK (operation IN ('CREATE', 'UPDATE', 'DELETE', 'CONSOLIDATE')),
    before_content TEXT,
    after_content TEXT,
    reason VARCHAR(255),
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(50),  -- 'agent' or user_id
    
    CONSTRAINT content_provided CHECK (
        (operation IN ('CREATE', 'UPDATE') AND after_content IS NOT NULL) OR
        (operation = 'DELETE' AND before_content IS NOT NULL)
    )
);

CREATE INDEX idx_audit_log_user ON memory_audit_log(user_id);
CREATE INDEX idx_audit_log_created_at ON memory_audit_log(created_at DESC);
```

---

## 4. Testing Strategy

### Unit Tests

```python
# tests/memory/test_embedding.py
async def test_embed_memory_content():
    content = "User prefers detailed feedback on talk structure"
    embedding = await embed_memory(content)
    assert len(embedding) == 1536
    assert all(isinstance(x, float) for x in embedding)

# tests/memory/test_deduplication.py
async def test_detect_duplicate_memory(high_similarity=0.95):
    """Cosine similarity > 0.95 should trigger UPDATE, not ADD"""
    existing = await store.get_memory("User prefers detailed feedback")
    new = "User wants detailed feedback iterations"  # Similar but not exact
    
    is_duplicate = await is_duplicate(existing, new, threshold=0.92)
    assert is_duplicate
    
# tests/memory/test_retrieval_ranking.py
async def test_rank_memories_by_recency():
    """Recent memories should rank higher"""
    old_memory = create_memory("Old fact", created_days_ago=60)
    new_memory = create_memory("New fact", created_days_ago=1)
    
    ranked = await rank_memories(query="fact", memories=[old_memory, new_memory])
    assert ranked[0].id == new_memory.id
```

### Integration Tests

```python
# tests/memory/test_memory_lifecycle.py
async def test_full_memory_lifecycle():
    """
    1. Agent creates memory from conversation
    2. Memory retrieved and injected into LLM prompt
    3. User views memory in dashboard
    4. User deletes memory
    5. Memory appears in audit log
    """
    # 1. Create
    memory = await memory_service.create_user_memory(
        user_id=TEST_USER,
        content="User prefers iterative feedback",
        memory_type="semantic"
    )
    
    # 2. Retrieve & inject
    retrieved = await memory_service.search(
        user_id=TEST_USER,
        query="What does user prefer?",
        limit=3
    )
    assert memory.id in [m.id for m in retrieved]
    
    # 3. View in API
    memories = await api.get_memories(user_id=TEST_USER)
    assert len(memories) > 0
    
    # 4. Delete
    await memory_service.delete_memory(memory.id, reason="User request")
    
    # 5. Verify in audit log
    audit = await memory_service.get_audit_log(user_id=TEST_USER)
    assert any(log.operation == "DELETE" and log.memory_id == memory.id for log in audit)
```

### End-to-End Tests

```python
# tests/e2e/test_memory_in_agent_workflow.py
async def test_agent_learns_from_conversation():
    """
    1. User starts chat with new agent instance
    2. User provides feedback on generated talk outline
    3. Agent learns preference from feedback
    4. In next chat, agent uses learned preference
    """
    # Chat 1: Initial conversation
    chat1 = await client.create_chat(project_id=TEST_PROJECT)
    
    response1 = await agent.generate_outline(
        chat_id=chat1.id,
        input="Create talk outline about AI"
    )
    
    # User feedback
    await client.provide_feedback(
        chat_id=chat1.id,
        feedback="I like the iterative structure; keep it"
    )
    
    # Verify memory created
    memories = await memory_service.search(
        project_id=TEST_PROJECT,
        query="structure"
    )
    assert any("iterative" in m.content for m in memories)
    
    # Chat 2: New conversation, same project
    chat2 = await client.create_chat(project_id=TEST_PROJECT)
    
    response2 = await agent.generate_outline(
        chat_id=chat2.id,
        input="Create talk outline about security"
    )
    
    # Verify agent uses learned preference
    assert "iterative" in response2 or "structure" in response2
```

---

## 5. Deployment Checklist

**Before launching agent-writable memory feature:**

- [ ] PostgreSQL with pgvector extension deployed
- [ ] Embedding service (OpenAI API key) configured
- [ ] Memory tables created with proper indexes
- [ ] Audit log table for compliance
- [ ] Backup strategy tested (daily snapshots)
- [ ] Unit tests passing (80%+ coverage)
- [ ] Integration tests passing
- [ ] E2E tests with real agent workflow
- [ ] Memory dashboard UI implemented
- [ ] Memory API endpoints tested (create, list, delete, export)
- [ ] Retention policy documented and communicated to users
- [ ] Privacy policy updated (what memories are stored, how long)
- [ ] GDPR/compliance review completed
- [ ] Monitoring dashboard set up (memory table growth, embedding latency)
- [ ] Alerting configured (embedding failures, anomalous memory sizes)
- [ ] User documentation written
- [ ] Support team trained on memory UI/API
- [ ] Beta launch to small user group
- [ ] Feedback collection and iteration cycle

---

**End of Implementation Guide**
