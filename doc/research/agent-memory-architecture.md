# Agent Memory Architecture Research Report

**Date:** 2026-04-04  
**Purpose:** Design multi-layer memory system for LangGraph-based learning platform  
**Scope:** Industry patterns, academic frameworks, injection strategies, anti-patterns

---

## Executive Summary

Modern AI agents require sophisticated memory systems to overcome the stateless nature of LLMs. Research across production systems (ChatGPT, Claude Projects, Amazon Bedrock, Gemini) and established frameworks (Mem0, LangGraph, Redis) reveals:

1. **Memory is multi-layered** — Short-term (conversation), long-term (persistent), with semantic/episodic/procedural subdivisions
2. **Scoping matters** — Global → User → Project → Chat hierarchy prevents information leakage
3. **Injection strategy is critical** — Token budget, ordering, and triggering determine effectiveness
4. **Agent-writable memory requires governance** — Deduplication, consolidation, user transparency, and controls prevent bloat
5. **Transparency is non-negotiable** — Users must see, edit, and control what agents remember

This report synthesizes patterns from ChatGPT Memory, Claude Projects, Amazon Bedrock AgentCore, Mem0, and LangGraph, providing concrete recommendations for your multi-layer memory design.

---

## 1. Industry Memory Patterns

### 1.1 ChatGPT Memory (OpenAI)

**Architecture:**
- **Saved Memories** — User-set facts agent retrieves across conversations (RAG-based)
- **Chat History Reference** — Model accesses previous conversations for context
- **Custom Instructions** — Read-only rules the agent always applies
- **Temporary Chat Mode** — Opt-out: doesn't use or create memories

**Key Features:**
- Automatic memory management: model keeps most relevant details, deprioritizes others
- Capacity limits: memories capped, with overflow to background
- Selective controls: users toggle memory and chat history independently
- Token efficiency: memories compressed; RAG reduces context bloat

**User Control:**
- View/edit/delete individual memories
- Clear all memories
- Turn memory on/off per tier (Plus/Pro only)
- Free users: lightweight short-term continuity only

**Relevance for LearnFlow:** User-managed custom instructions map to your needs; automatic consolidation pattern validates agent-writable memory approach.

---

### 1.2 Claude Projects (Anthropic)

**Architecture:**
- **System Prompt** — Read-only per-project instructions (single file or modular in `.claude/rules/`)
- **Knowledge Base** — RAG over uploaded documents (PDF, MD, code)
- **Auto Memory** — Agent-writable notes across sessions (without user management)
- **Per-session Context** — Conversation history within a chat thread

**Scoping:**
- Project-level isolation (no cross-project inheritance, though planned as hub-and-spoke model)
- System prompt + knowledge base injected into every chat in project
- Auto memory optional; can be disabled

**Key Design Insight:**
- Separates **static/authored** (system prompt, knowledge) from **dynamic/learned** (auto memory)
- No user management of auto memory; agent autonomously learns preferences, architecture notes, style
- Transparency: memory files are plain markdown, human-readable

**Relevance for LearnFlow:** Project-level system prompt + knowledge storage directly maps to your "Project Memory"; auto memory pattern validates agent-writable layer.

---

### 1.3 Amazon Bedrock AgentCore Memory

**Memory Types:**
- **Short-term Memory** — Raw interactions within single session (≤8 hours or 15 min inactivity)
- **Long-term Memory** — Structured facts extracted from interactions (summaries, preferences, knowledge)

**Architecture:**
- **Memory Strategy** — Configuration defining how to process conversational data and extract facts
- **Semantic Search** — Retrieves most relevant memory records based on query similarity
- **Branching** — Create alternative conversation paths from specific points in history

**Scoping & Operations:**
- User-scoped memory: facts stored per user context
- Operations: extract, consolidate, retrieve, search
- Session isolation: memory branching allows A/B testing different paths

**Key Features:**
- Automatic summarization of raw conversations
- Structured extraction of facts, preferences, summaries
- Semantic search for retrieval (cosine similarity)

**Relevance for LearnFlow:** Memory strategies pattern validates need for explicit memory extraction configuration; semantic search pattern for retrieval is standard.

---

### 1.4 Google Gemini Agent Memory

**Implementations:**
1. **Always-On Memory Agent** — Lightweight background process that reads, thinks, writes structured memory (no vector DB needed)
2. **Gemini Code Assist Memory** — Dynamic memory of team coding standards/style from pull request feedback
3. **Vertex AI Memory Bank** — Persists stylistic preferences across conversations (InMemoryMemoryService for prototyping)
4. **Gemini Enterprise Memory** — Personal memory from email, calendar, documents; learns work patterns
5. **Gemini CLI Memory** — File-based memory with `save_memory` tool (agent-controlled)

**Key Pattern:**
Multiple implementations range from simple file-based (markdown, searchable in any editor) to sophisticated graph-based. Flexibility in storage backend (in-memory, file, database) enables different use cases.

**Relevance for LearnFlow:** File-based + database-backed hybrid approach gives transparency (users can read memory files) and durability.

---

## 2. Academic Memory Taxonomy

### 2.1 CoALA Framework (Cognition-inspired)

From research and production systems, a four-tier taxonomy emerges:

| Memory Type | Purpose | Retention | Agent Access | Example |
|---|---|---|---|---|
| **Working** | Current interaction context | Single conversation | Active (system prompt) | Current chat history, reasoning steps |
| **Semantic** | Factual knowledge, structured facts | Cross-conversation | RAG retrieval | User preferences, project goals, facts |
| **Episodic** | Specific experiences with temporal/context details | Cross-conversation | Vector search (similarity) | "User asked about X on 2026-02-15; solution was Y" |
| **Procedural** | Instructions, rules, workflows | Persistent (immutable by agent) | System prompt, tools | Custom instructions, system rules, tool definitions |

**Key Insight:** Production systems blend types rather than strictly separating them. ChatGPT's "saved memories" are semantic + episodic hybrid. Mem0 unifies all types with multi-level scoping.

---

### 2.2 Memory Lifecycle Operations

Core operations regardless of memory type:

| Operation | Purpose | Trigger | Risk |
|---|---|---|---|
| **ADD** | Store new fact/experience | Agent autonomous OR user request | Memory bloat; prefer selective ADD |
| **UPDATE** | Modify existing memory (not overwrite) | New info revises old understanding | Risk of losing history; prefer versioning |
| **DELETE** | Remove obsolete information | Manual user request OR decay mechanism | Data loss; rare in practice |
| **NOOP** | Recognize no action needed | Duplicate/irrelevant detected | Risk: false negative (irrelevant stored) < false positive (relevant deleted) |
| **RETRIEVE** | Fetch relevant memories for current task | On every agent turn | Retrieval quality depends on embeddings; bad embeddings → garbage in, garbage out |
| **CONSOLIDATE** | Merge redundant, dedup, summarize | Periodic background task | Lossy compression; need thresholds to preserve distinct memories |

**Critical Insight:** UPDATE is most underutilized operation. Naive systems ADD everything; production systems distinguish between "new fact" vs "revision of existing fact."

---

## 3. Scoping & Isolation Hierarchy

All production systems implement multi-level scoping to prevent information leakage and enable proper access control:

```
Global/System Level
    ↓
User Level (cross-project)
    ↓
Project Level (per-project)
    ↓
Chat/Session Level (per conversation)
    ↓
Turn Level (current request)
```

### 3.1 Scoping in Production Systems

| System | Global | User | Project | Chat | Turn |
|---|---|---|---|---|---|
| **ChatGPT** | Model training | Saved memories, preferences | — | Chat history | Context window |
| **Claude Projects** | — | Auto memory | System prompt, KB, auto memory | Conversation | Active context |
| **Bedrock AgentCore** | — | User ID | — | Session (8h) | Immediate context |
| **Mem0** | app_id | user_id | — | run_id | — |

### 3.2 Recommended Scoping for LearnFlow

```
learnflow-ai (global)
├── User Level
│   ├── Custom Instructions (read-only, user-managed)
│   └── User Memory (cross-project, agent-writable)
│       └── Preferences, work style, general interests
├── Project Level
│   ├── System Prompt (per-project rules)
│   ├── Knowledge Sphere (project-specific docs, context)
│   └── Project Memory (agent-writable, project-specific)
│       └── Talk outline, content generated, user feedback
└── Chat Level
    └── Conversation History (short-term, checkpointed)
```

**Key Design:**
- **Custom Instructions** → Procedural memory (read-only)
- **User Memory** → Semantic + Episodic (cross-project, agent-writable)
- **Project Memory** → Semantic + Episodic (project-scoped, agent-writable)
- **Knowledge Sphere** → Semantic (structured documents, RAG)
- **Conversation** → Working memory (context window, checkpointed)

---

## 4. Memory Injection Strategies

### 4.1 Token Budget Architecture

Token usage is the primary constraint. Structure memory injection with explicit budgets:

```
System Prompt (base)
├── Core Instructions: ~200 tokens
├── Tool Definitions: ~300 tokens
├── Custom Instructions (if user-set): ≤250 tokens
└── Memory Injection Block: ≤500 tokens (burst)
    ├── Project System Prompt: ≤200 tokens
    ├── User Memory: ≤150 tokens (top-k retrieval)
    └── Project Memory: ≤150 tokens (top-k retrieval)

Evidence/Context Block: ≤1200 tokens
├── Knowledge Sphere RAG results: ≤800 tokens
├── Conversation history: ≤400 tokens
└── Retrieved documents: ≤400 tokens (if needed)

Working Context: ≤300 tokens
└── Current turn input + state
```

**Total baseline:** ~2500 tokens for system message (before user input), leaving ~1500 for conversation.

### 4.2 Injection Timing & Ordering

Research shows **ordering and timing matter as much as content**. Models underutilize mid-context information.

**Optimal injection order:**

1. **Core system instructions first** — Agent role, constraints
2. **Custom instructions next** — User-provided rules (high priority)
3. **Conversation history** — Recent turns (models attend well to recency)
4. **Memory burst before critical actions** — Right before tool selection, final answer
5. **Evidence/context (RAG results) mid-prompt** — Knowledge Sphere documents
6. **Project system prompt** — Project-specific rules

**Anti-pattern:** Dumping all memory at the end of system prompt. Retrieve and inject only **top-k most relevant** memories using vector similarity.

### 4.3 Memory Retrieval Strategy (RAG)

For both User Memory and Project Memory:

```python
# On each agent turn:
1. User query → embedding
2. Semantic search in memory store: retrieve top-5 most similar
3. Filter by relevance (cosine similarity > 0.7)
4. Rerank by recency (recent memories weighted higher)
5. Inject top-3 into system prompt (token budget: ~150 tokens)
```

**Mem0 approach:** Extract + Update pipeline with deduplication

```python
# Extraction phase:
1. Latest user message
2. Rolling summary of conversation
3. M most recent messages
→ LLM extracts candidate memories

# Update phase:
1. Find top-S similar existing memories
2. Compare extracted vs existing
3. Apply operation: ADD / UPDATE / NOOP / CONSOLIDATE
```

---

## 5. Agent-Writable Memory Management

### 5.1 When Should Agent Write to Memory?

**Explicit triggers (safe, user-visible):**
- User requests: "Remember I prefer X"
- Agent asks permission: "Should I save this preference?"
- Structured extraction after milestone completion

**Autonomous triggers (risky, requires governance):**
- After user provides feedback on generated content
- When user confirms/approves agent output
- Periodic consolidation of interaction patterns

**Never autonomous (violates trust):**
- Storing unprompted assumptions about user
- Silently updating memory without user visibility
- Storing sensitive data (health, finance) without explicit consent

**Recommended for LearnFlow:**
1. **Explicit:** User-initiated "Remember..." via UI
2. **Semi-autonomous:** After user feedback on talk outline (ask permission first)
3. **Autonomous:** Project Memory updates after each successful chat (but user-visible in memory UI)

---

### 5.2 Memory Bloat & Consolidation

**The Problem:** Without active consolidation, agent memory becomes 60-70% noise (small talk, transient reasoning, repetition). Retrieval quality degrades; costs rise; agent becomes slower.

**Consolidation Strategy (Mem0 pattern):**

```
Frequency: Every N turns or periodically (e.g., after 50 messages)

Pipeline:
1. Identify candidate memories for consolidation
   └── Same topic/entity, temporal proximity, similar embedding

2. Deduplication (write-side)
   └── Before adding new memory: check cosine similarity > 0.92
   └── If similar exists: UPDATE instead of ADD

3. Merge (consolidation-side)
   └── After accumulation: merge similar memories > 0.95 similarity
   └── Combine into single canonical memory with history

4. Delete (rare)
   └── Only explicit user deletion or decay policy (e.g., >6 months old + never accessed)

5. Summarization
   └── Verbose episodic memories → concise semantic facts
   └── "User spent 3 sessions perfecting talk outline about X" → "Preference: detailed iterative feedback on talk structure"
```

**Key Thresholds:**
- Write-side dedup: cosine similarity > 0.92 (conservative, prevents information loss)
- Consolidation merge: cosine similarity > 0.95 (aggressive, reduces redundancy)
- Recency weight: recent memories (< 1 week) ranked higher in retrieval

---

### 5.3 User Control & Transparency

**ChatGPT Pattern:** Automatic consolidation; users can view/edit/delete individual memories via UI.

**Gemini CLI Pattern:** Markdown file with memories; users read/edit in text editor (maximum transparency).

**Recommended Hybrid for LearnFlow:**

1. **Memory Dashboard UI** (for users)
   - View all User Memory facts (searchable, filterable)
   - View all Project Memory facts
   - Edit memory text directly
   - Delete specific memories
   - See metadata: created date, last accessed, relevance score

2. **File-based backup** (for transparency & compliance)
   - Export User Memory as JSON/Markdown
   - Export Project Memory as JSON/Markdown
   - Audit trail: changes timestamped, user-initiated

3. **Default retention policy**
   - User Memory: indefinite (user can delete)
   - Project Memory: indefinite (user can delete)
   - Conversation history: 90 days in search; 12 months available on request
   - Sensitive data (if captured): explicit 30-day TTL unless user extends

---

## 6. LangGraph-Specific Memory Patterns

### 6.1 State-Based Memory in LangGraph

LangGraph handles memory through **checkpointing + state management**:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from typing import Annotated
import operator

class WorkflowState(BaseModel):
    # Working memory (short-term, current conversation)
    messages: Annotated[List[BaseMessage], operator.add] = []
    current_turn_context: dict = {}
    
    # Semantic memory (facts about user/project)
    user_preferences: dict = {}
    project_goals: str = ""
    
    # Episodic memory (past interactions)
    recent_interactions: Annotated[List[dict], operator.add] = []
    
    # Procedural memory (system rules, tools)
    custom_instructions: str = ""

# Persistence: one thread_id per session
async def run_workflow(thread_id: str):
    async with AsyncPostgresSaver.from_conn_string(DB_URL) as saver:
        graph = workflow.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": thread_id}}
        
        # State automatically persisted; resumable across server restarts
        async for event in graph.astream(input_state, cfg):
            yield event
```

**Key Points:**
- **Checkpointer** stores full state at each step; supports interrupts and recovery
- **thread_id** scopes state; each session/conversation = separate thread
- **operator.add** enables accumulation (append-semantics) for multi-turn memories
- **aget_state()** retrieves current state; supports HITL workflows

### 6.2 Memory Injection in Nodes

```python
async def my_node(state, config) -> Command:
    thread_id = config["configurable"]["thread_id"]
    
    # Retrieve top-k relevant memories from external store
    user_memories = await fetch_user_memories(
        user_id=get_user_id(thread_id),
        query=state.current_turn_context,
        top_k=5
    )
    
    project_memories = await fetch_project_memories(
        project_id=state.project_id,
        query=state.current_turn_context,
        top_k=5
    )
    
    # Build memory-augmented context
    memory_context = format_memory_burst(
        user_memories=user_memories,
        project_memories=project_memories,
        budget_tokens=150
    )
    
    # Call LLM with memory injection
    response = await llm.ainvoke(
        state.messages + [
            SystemMessage(content=memory_context),
            HumanMessage(content=state.input)
        ]
    )
    
    # Update state with new interaction
    return Command(
        update={
            "messages": [AIMessage(content=response)],
            "recent_interactions": [{
                "timestamp": now(),
                "user_input": state.input,
                "agent_output": response
            }]
        },
        goto="next_node"
    )
```

---

## 7. Anti-Patterns & Pitfalls

### 7.1 Common Memory Mistakes

| Anti-Pattern | Problem | Consequence | Fix |
|---|---|---|---|
| **Memory Overload** | Add all interactions to memory | Agent attends to thousands of irrelevant facts; paralysis, hallucination | Selective ADD; consolidation; top-k retrieval only |
| **Error Propagation** | Agent stores mistakes as "lessons learned" | Errors compound; same mistake repeated | Separate error log from lessons; manual review before memory ADD |
| **Irrelevant Retrieval** | Bad embeddings, broad queries return noise | Agent confused by garbage retrieved | Monitor embedding quality; rerank by recency; set similarity thresholds |
| **Memory Fragmentation** | Separate DBs for vectors, graphs, relational | Inconsistent state; write-failure cascades | Single memory store OR distributed transactions |
| **No Update Operation** | Agent always ADD instead of UPDATE | Duplicate facts accumulate; context bloat | Implement UPDATE explicitly; detect revisions vs new facts |
| **Silent Memory Changes** | Agent updates memory without user visibility | Users don't know what agent learned; lost trust | Memory dashboard; explicit user consent for autonomous updates |
| **No Retention Policy** | Memories kept indefinitely | Compliance/privacy violations (GDPR, HIPAA) | Implement TTL per memory type; user controls |
| **Over-reliance on Memory** | Agent forgets to use reasoning; just retrieves | Agent becomes reactive, not proactive | Balance memory + reasoning; don't inject all memories |

### 7.2 Memory Consistency Issues

**Problem:** Distributed memory systems (vectors in Pinecone, graphs in Neo4j, relational in Postgres) have no shared transaction boundaries.

**Scenario:** Add memory to vector DB succeeds; graph DB write fails → memory in inconsistent state → agent hallucinates based on partial information.

**Solutions:**
1. **Single data store** — Use Redis (vectors + relational in one DB) or PostgreSQL with PGVector extension
2. **Distributed transactions** — Implement saga pattern: all writes succeed or all roll back
3. **Audit trail** — Log every memory operation; replay on failure

---

## 8. Design Recommendations for LearnFlow

### 8.1 Proposed Multi-Layer Architecture

```
LearnFlow Memory System
├── Layer 1: Working Memory (LangGraph state + checkpoints)
│   ├── Conversation history (messages)
│   ├── Current turn context
│   ├── Intermediate reasoning
│   └── Scope: per-chat, ephemeral (session-scoped)
│
├── Layer 2: Procedural Memory (read-only, user/system-managed)
│   ├── Custom Instructions (user-set rules)
│   ├── System Prompt (agent role)
│   ├── Tool definitions
│   └── Scope: global/user/project, immutable
│
├── Layer 3: Project Memory (agent-writable, project-scoped)
│   ├── Talk outline generations (episodic)
│   ├── User feedback on content (episodic)
│   ├── Project goals, constraints (semantic)
│   └── Content patterns, style preferences for this project (semantic)
│   └── Scope: per-project, agent can UPDATE/ADD with user visibility
│
├── Layer 4: User Memory (agent-writable, cross-project)
│   ├── General work style preferences (semantic)
│   ├── Content preferences across projects (semantic)
│   ├── Past project outcomes (episodic, aggregated)
│   └── User feedback patterns (episodic → semantic)
│   └── Scope: global (user-level), agent can UPDATE/ADD with user visibility
│
├── Layer 5: Knowledge Sphere (read-only, RAG)
│   ├── Project documents (PDF, markdown, etc.)
│   ├── External research (firecrawl-sourced)
│   └── Scope: per-project, retrieved on-demand
│
└── Layer 6: Semantic Search Index
    ├── Vector embeddings of all memories
    ├── Cosine similarity for retrieval
    └── Supports top-k retrieval for injection
```

### 8.2 Implementation Roadmap

**Phase 1 (MVP):**
- Working Memory: LangGraph checkpoints (conversation history)
- Procedural Memory: Custom Instructions (user-managed via UI)
- Project Memory: Manual user notes (Knowledge Sphere enhancement)
- Injection: System prompt + conversation history only

**Phase 2 (Post-MVP):**
- Agent-writable User Memory: Autonomous preference extraction (with user visibility)
- Agent-writable Project Memory: Content patterns, feedback integration
- Consolidation: Periodic dedup + summarization
- Retrieval: Top-k semantic search for memory injection
- Dashboard: View/edit/delete memory UI

**Phase 3 (Optimization):**
- Decay policy: TTL per memory type
- Multi-project inheritance: Hub-and-spoke scoping
- Privacy controls: Per-memory retention settings
- Compliance: GDPR deletion, audit trails

### 8.3 Key Decisions Needed

| Decision | Options | Recommendation | Rationale |
|---|---|---|---|
| **Memory Storage Backend** | PostgreSQL (pgvector), Redis, separate vector DB | PostgreSQL + pgvector | Single data store prevents inconsistency; pgvector mature for vectors + relational data |
| **Consolidation Frequency** | Per-turn, per-N-turns, periodic background | Per-50-messages + nightly background | Balances freshness vs compute; nightly consolidation prevents bloat |
| **User Transparency** | Automatic (no dashboard), explicit (dashboard UI), file-based | Dashboard UI + exportable JSON | Satisfies trust requirement; supports compliance audits |
| **Agent Autonomy** | Manual approval only, semi-autonomous (ask first), full autonomous | Semi-autonomous (ask after user feedback) | Balances UX (don't ask for every memory) + transparency (show what agent learned) |
| **Memory Injection** | All memories, top-k retrieval, configurable per-node | Top-k retrieval with token budget | Prevents bloat; ensures relevant memories injected; respects token limits |
| **Scoping Model** | Flat (no inheritance), hierarchical (project ← user) | Hierarchical: global → user → project | Enables cross-project learning; prevents duplication |

---

## 9. References & Sources

### Production System Documentation
- [ChatGPT Memory FAQ](https://help.openai.com/en/articles/8590148-memory-faq)
- [OpenAI Memory Feature](https://openai.com/index/memory-and-new-controls-for-chatgpt/)
- [Claude Projects Memory](https://code.claude.com/docs/en/memory)
- [Amazon Bedrock AgentCore Memory](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/)
- [AWS Bedrock Memory Types](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html)

### Memory Frameworks
- [Mem0: Building Production-Ready AI Agents](https://mem0.ai/)
- [Mem0 Documentation](https://docs.mem0.ai/platform/overview)
- [Mem0 Research Paper](https://arxiv.org/pdf/2504.19413)
- [AWS Bedrock + Mem0 Integration](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/)

### Academic & Engineering Research
- [Memory in AI Agents - Leonie Monigatti](https://www.leoniemonigatti.com/blog/memory-in-ai-agents.html)
- [Redis Agent Memory Architecture](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [AI Agent Memory: 26% Accuracy Boost](https://mem0.ai/research)
- [Mem0: Multi-Agent Memory Systems](https://mem0.ai/blog/multi-agent-memory-systems)
- [Memory Engineering for Production](https://medium.com/@mjgmario/memory-engineering-for-ai-agents-how-to-build-real-long-term-memory-and-avoid-production-1d4e5266595c)
- [Agent Memory Consolidation System](https://deepwiki.com/frdel/agent-zero/4.3-memory-consolidation-system)
- [Governed Memory Architecture](https://arxiv.org/html/2603.17787)
- [Memory for Autonomous LLM Agents](https://arxiv.org/html/2603.07670)

### Practical Guides
- [Token Optimization Strategies](https://developer.ibm.com/articles/awb-token-optimization-backbone-of-effective-prompt-engineering/)
- [Context Engineering in Agent Memory](https://medium.com/agenticais/context-engineering-in-agent-982cb4d36293)
- [OpenAI SDK Context Personalization](https://cookbook.openai.com/examples/agents_sdk/context_personalization)
- [AI Agents and Memory: Privacy & Power](https://www.newamerica.org/insights/ai-agents-and-memory/)
- [Salesforce Agentic Memory](https://engineering.salesforce.com/how-agentic-memory-enables-durable-reliable-ai-agents-across-millions-of-enterprise-users/)

### LangGraph Patterns
- [LangGraph Memory & Checkpointing](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangGraph Long-term Memory](https://docs.langchain.com/oss/python/langchain/long-term-memory)

---

## Appendix: Token Budget Template

```
System Message Structure (2500 tokens max)
├── Core Instructions (200 tokens)
│   └── Agent role, primary objective, constraints
│
├── Procedural Memory (250 tokens)
│   ├── Custom Instructions (user-set)
│   └── System rules
│
├── Memory Injection Burst (500 tokens)
│   ├── User Memory (top-3, 150 tokens)
│   ├── Project Memory (top-3, 150 tokens)
│   └── Recent interactions summary (200 tokens)
│
├── Tool Definitions (300 tokens)
│   └── Available tools, parameters, constraints
│
├── Context/Evidence Block (1200 tokens)
│   ├── Knowledge Sphere RAG (800 tokens)
│   ├── Conversation history (300 tokens)
│   └── Retrieved documents (100 tokens)
│
└── Working Context (150 tokens)
    └── Current turn input, immediate state

Total: ~2500 tokens (before user input)
Leaves ~1500 tokens for conversation (8K context model)
```

---

**End of Report**
