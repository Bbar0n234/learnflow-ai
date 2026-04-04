# LangGraph Store: Comprehensive Technical Deep-Dive

## Executive Summary

LangGraph Store is a **namespace-keyed key-value persistence layer** designed for cross-thread, cross-conversation long-term memory in agents. It supports:
- Basic operations (put, get, delete, search)
- Optional semantic/vector search via embeddings
- Namespace-based hierarchical organization
- Multiple backend implementations (InMemoryStore, AsyncPostgresStore, RedisStore)

**Status for multi-layer memory expansion:** Store can serve as a unified backend for your architecture, but certain patterns require careful design to avoid querying limitations.

---

## 1. Store API Methods

### Core Operations (Sync & Async)

All methods have async variants prefixed with `a` (e.g., `aput`, `aget`, `asearch`, `adelete`).

#### **aput** - Store/Update Item
```python
await store.aput(
    namespace: tuple[str, ...],
    key: str,
    value: dict,
    index: bool | list[str] | None = None  # Per-item indexing control
)
```
- **namespace**: Tuple of strings, acts like a path hierarchy
- **key**: Unique identifier within the namespace
- **value**: JSON-serializable dict (stored as-is)
- **index**: Optional, controls per-item embedding indexing:
  - `True` (default): Embed all fields
  - `False`: Store but don't embed (not searchable by query)
  - `list[str]`: Embed only specified fields (e.g., `["$"]` for entire value, `["description"]` for specific field)
- **Return**: None
- **Timestamps**: Store automatically manages `created_at` and `updated_at` (immutable after creation)

#### **aget** - Retrieve Single Item
```python
item = await store.aget(namespace: tuple[str, ...], key: str) -> Item | None
```
- **Return**: `Item` object (see structure below) or None if not found
- **Item structure:**
  ```python
  @dataclass
  class Item:
      value: dict           # Your stored JSON
      key: str              # The key
      namespace: list[str]  # Namespace as list (serialized from tuple)
      created_at: str       # ISO 8601 timestamp
      updated_at: str       # ISO 8601 timestamp
  ```

#### **asearch** - Search Items in Namespace
```python
items = await store.asearch(
    namespace: tuple[str, ...],
    query: str | None = None,        # Natural language query for semantic search
    filter: dict | None = None,       # Exact-match filter on value fields
    limit: int = 10,
    offset: int = 0
) -> list[Item]
```
- **query**: If provided, performs semantic/vector search (requires embedding index configured). Returns items sorted by vector similarity.
- **filter**: Dictionary for exact-match filtering on nested value fields
  - Example: `filter={"my-key": "my-value"}` matches items where `item.value["my-key"] == "my-value"`
  - Does NOT support partial/fuzzy matching
- **limit/offset**: Pagination
- **Return**: List of `Item` objects ordered by `updated_at` (most recent last)
- **Key behavior**: `asearch()` without `query` or `filter` lists ALL items in that namespace

#### **adelete** - Remove Item
```python
await store.adelete(namespace: tuple[str, ...], key: str)
```
- Deletes the item, no return value
- Silent if item doesn't exist

#### **alist_namespaces** - List All Namespaces
```python
namespaces = await store.alist_namespaces(
    match: str | None = None  # Prefix match (not glob)
) -> list[tuple[str, ...]]
```
- **match**: Prefix filter (e.g., `match="user"` finds all namespaces starting with `("user", ...)`). Comparison is tuple-based, not string-based.
- **Return**: List of namespace tuples that exist (have at least one item)
- **Limitation**: No wildcard/glob support; only exact prefix matching on the tuple path

---

## 2. Namespace Design & Query Capabilities

### Hierarchical Organization

Namespaces are **tuple-based paths**. Depth is unlimited in theory but practically indexed as flat storage:

```python
# Examples from your project
("project", "a1b2c3d4-...", "sphere")       # Knowledge Sphere per project
("user", "user-123", "preferences")         # User-wide preferences
("user", "user-123", "instructions")        # Custom instructions per user
("user", "user-123", "cross-project-notes") # Cross-project user memory
("organization", "org-456", "guidelines")   # Org-level shared memory
```

### Query Patterns & Limitations

**What WORKS:**
- Exact namespace match: `asearch(("user", "user-123", "preferences"))` returns all items in that exact namespace
- Prefix namespace match: `alist_namespaces(match=("user",))` lists all `("user", ...)` namespaces
- Semantic search within a namespace: Query-based search across all items in a single namespace

**What DOES NOT WORK (architectural gap):**
- **Wildcard queries**: Cannot query `("user", "*", "preferences")` to fetch all users' preferences in one operation
- **Hierarchical prefix queries**: Cannot fetch all items under `("user", "user-123")` regardless of sub-namespace without iterating manually
- **Cross-namespace queries**: Must query each namespace separately; no way to search across multiple namespaces atomically

**Workaround for hierarchical queries:**
```python
# To get all memories for a user across different categories:
categories = ["preferences", "instructions", "notes"]
all_items = []
for category in categories:
    items = await store.asearch(("user", user_id, category))
    all_items.extend(items)
```

---

## 3. Indexing & Vector Search

### Index Configuration

Configured at **store initialization**, not per-operation:

```python
from langgraph.store.base import IndexConfig
from langgraph.store.postgres import AsyncPostgresStore
from langchain.embeddings import init_embeddings

# Initialize with semantic search
store = AsyncPostgresStore(
    connection_string=DB_URL,
    index=IndexConfig(
        embed=init_embeddings("openai:text-embedding-3-small"),  # Embedding callable
        dims=1536,                                                # Embedding dimension
        fields=["$"]                                              # Fields to embed: "$" = entire value, or ["description", "content"]
    )
)
```

### Per-Item Indexing Control

You can selectively control indexing on a per-put basis:

```python
# Embed this item (uses store's configured embedding)
await store.aput(ns, key, {"description": "...", "content": "..."})  # Default: index=True

# Don't embed (store but not searchable)
await store.aput(ns, key, {"secret": "..."}, index=False)

# Embed only specific fields
await store.aput(ns, key, {"meta": "...", "sensitive": "..."}, index=["meta"])
```

### Vector Search Behavior

- **Semantic search**: `asearch(namespace, query="what did user say about pizza?")` returns items sorted by cosine similarity of embeddings
- **No custom vector input**: You cannot provide pre-computed vectors; embeddings are computed via the configured embedding function
- **Ranking**: Results ordered by similarity score (highest similarity first)
- **Availability**: Only when `IndexConfig` is provided at initialization; cannot enable/disable dynamically

---

## 4. Metadata Filtering

### Supported Filtering

The `filter` parameter in `asearch()` only supports **exact-match key-value filtering**:

```python
# Only items where item.value["status"] == "active"
items = await store.asearch(ns, filter={"status": "active"})

# Nested field matching (dict with nested keys)
items = await store.asearch(ns, filter={"user": {"name": "Alice"}})
# Matches items where item.value["user"]["name"] == "Alice"
```

### NOT Supported

- Fuzzy/partial matching
- Range queries (`>`, `<`, `>=`, `<=`)
- Array/list membership
- Regex patterns

**Workaround**: Fetch all items and filter client-side, or denormalize data to make exact-match filters work.

---

## 5. Async API Deep-Dive

All operations are async-first. Method signatures:

```python
# Async versions (required for LangGraph)
await store.aput(...)       # Async write
item = await store.aget(..) # Async read
items = await store.asearch(...)  # Async search
await store.adelete(...)    # Async delete
namespaces = await store.alist_namespaces(...)  # Async list
```

**Connection Pooling**: `AsyncPostgresStore` manages a connection pool under the hood. Use context manager:

```python
async with AsyncPostgresStore.from_conn_string(DB_URL) as store:
    await store.setup()  # Create tables if needed
    # Use store...
```

---

## 6. AsyncPostgresStore Specifics

### Initialization

```python
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.base import IndexConfig

async def init_store():
    store = AsyncPostgresStore(
        connection_string="postgresql://user:pass@localhost/db",
        index=IndexConfig(
            embed=init_embeddings("openai:text-embedding-3-small"),
            dims=1536,
            fields=["$"]
        )
    )
    async with store:
        await store.setup()  # Creates: store_items, store_namespaces tables + vector index
        # Use store...
```

### PostgreSQL Schema (Implicit)

AsyncPostgresStore uses two tables:
- `store_items`: `(namespace[str[]], key[str], value[jsonb], created_at, updated_at, embedding[vector])`
- `store_namespaces`: Tracks which namespaces exist

Vector search uses pgvector extension (created automatically if available).

### Performance Characteristics

- **aget**: O(1) - direct key lookup
- **asearch** (no query/filter): O(n) - full table scan of namespace
- **asearch** (with query): O(n·m) where m = embedding dimension - vector similarity search
- **asearch** (with filter): O(n) - filter evaluated on fetched rows
- **alist_namespaces**: O(k) where k = number of distinct namespaces

**Capacity**: PostgreSQL text/jsonb limits; practically stores GB-scale data. Individual item value size: nominally unlimited JSON (tested up to MBs per item).

---

## 7. Official Memory Patterns from LangGraph Docs

### Pattern 1: Long-term User Memory (Semantic)

**Use case**: Store user preferences, interaction history, and recall by relevance.

```python
namespace = (user_id, "memories")

# Write diverse memories
await store.aput(
    namespace, 
    str(uuid.uuid4()), 
    {"memory": "User likes Italian food", "type": "preference"}
)

# Semantic search across all user memories
memories = await store.asearch(
    namespace,
    query="What does the user like to eat?",
    limit=5
)
```

**Recommended index**: `IndexConfig(fields=["$"])` to search entire memory objects.

### Pattern 2: Cross-Thread Shared Memory

**Use case**: Information persists across conversations (threads) with the same user.

```python
# Thread isolation via checkpointer (per thread_id)
# Shared memory via Store (per user_id)

# Graph compiled with both:
graph.compile(checkpointer=checkpointer, store=store)

# In a node:
async def call_model(state, runtime):
    user_id = runtime.context.user_id
    
    # Fetch shared memory (survives thread boundaries)
    memories = await runtime.store.asearch((user_id, "shared"), limit=10)
    
    # Use in prompt, then update for next thread
    await runtime.store.aput((user_id, "shared"), key, {...})
```

### Pattern 3: Multiple Memory Types with Different Access

**Design**: Namespace per memory type, segregate read-only from read-write.

```python
# Read-only: project documentation (updated externally)
docs = await store.asearch(("docs", "public"), limit=100)

# Read-write: user customizations
await store.aput(("user", user_id, "custom"), key, {...})

# Transient: temporary state (purged via TTL or manually)
await store.aput(("session", session_id, "temp"), key, {...})
```

### Pattern 4: Hierarchical Memory Organization

**Problem**: Nested categories (user → project → conversation memories).

**Solution**: Flat namespaces with composite keys:

```python
# Namespace for all user memories
ns = (user_id, "memories")

# Keys encode hierarchy
key = f"project:{project_id}:conversation:{conv_id}:memory"
await store.aput(ns, key, {"content": "..."})

# Retrieve by prefix within key
items = await store.asearch(ns, limit=100)
filtered = [i for i in items if f"project:{project_id}" in i.key]
```

**Alternative**: Deeper namespace tuple (but requires iteration for cross-project queries):

```python
ns = (user_id, "projects", project_id, "memories")
# Iteration needed for cross-project discovery
```

---

## 8. Limitations & Constraints

### Hard Limits

1. **No wildcard namespace queries**: Cannot do `alist_namespaces(match=("user", "*"))`; must iterate
2. **No cross-namespace search**: Each `asearch()` operates on a single namespace
3. **Exact-match filtering only**: `filter` parameter doesn't support operators or partial matching
4. **No custom indexes**: Cannot create indexes on specific value fields; all indexing is via configured embedding
5. **No transactions**: Writes are atomic per item, not across multiple items

### Design Constraints

1. **Item ordering**: Results always ordered by `updated_at`; no custom sort keys
2. **Pagination overhead**: `asearch(..., limit=10, offset=100)` fetches all 100 rows then skips; not optimized
3. **Embedding computation**: Every `aput` (with index=True) triggers embedding API call; batch operations require manual looping
4. **Namespace enumeration**: `alist_namespaces()` is full scan; slow on systems with millions of namespaces

### Query Gaps for Your Use Case

**Cannot efficiently query:**
- "Get all memories for a user across all projects" (cross-namespace)
- "Get all users in an organization" (hierarchical wildcard)
- "Find all items updated in last 24 hours" (time-range filtering)

**Workaround**: Application-level caching or denormalized index.

---

## 9. Recommended Multi-Layer Memory Architecture

Based on Store's strengths and limitations:

### Namespace Strategy
```python
# Layer 1: Project-scoped memory
("project", project_id, "sphere")           # Knowledge Sphere (your current pattern)

# Layer 2: User-wide preferences & settings
("user", user_id, "preferences")            # User preferences (read-heavy, rarely updated)

# Layer 3: Custom instructions (user cross-project)
("user", user_id, "instructions")           # Stored instructions (agent-maintained)

# Layer 4: Cross-project user memory (semantic)
("user", user_id, "memory", "semantic")     # Memories indexed for search

# Layer 5: Organization guidelines (shared)
("org", org_id, "guidelines")               # Org-level shared reference

# Layer 6: Transient session state (TTL)
("session", session_id, "temp")             # Temporary, auto-cleaned
```

### Implementation Patterns

1. **Preferences** (read-only-ish):
   - Single key per namespace: `await store.aget((user_id, "preferences"), "settings")`
   - Update entire object atomically

2. **Custom Instructions** (agent-maintained):
   - Similar to Knowledge Sphere: composite value with `{"description": str, "content": str}`
   - Use `asearch(("user", user_id, "instructions"))` to list

3. **Semantic Memories** (cross-project user memory):
   - Enable embedding index on `fields=["$"]`
   - Semantic search: `await store.asearch(("user", user_id, "memory", "semantic"), query=...)`
   - Denormalize context: include `project_id` in each memory value for filtering

4. **Cross-project queries**: Store a query index separately (e.g., Redis or database view)
   - When adding memory: `SET user:{user_id}:project_memories {project_id}:1` (Redis set)
   - Iterate projects, then fetch from Store per project

---

## 10. Code Examples

### Example 1: Multi-type Memory in Single Project

```python
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.base import IndexConfig
import uuid
from datetime import datetime, timezone

# Initialize
store = AsyncPostgresStore(
    connection_string=DB_URL,
    index=IndexConfig(
        embed=init_embeddings("openai:text-embedding-3-small"),
        dims=1536,
        fields=["content", "description"]  # Embed content fields only
    )
)

async def setup():
    await store.setup()

# Store preferences
async def save_user_preferences(user_id: str, prefs: dict):
    ns = (user_id, "preferences")
    await store.aput(ns, "settings", prefs)

# Retrieve preferences
async def get_user_preferences(user_id: str) -> dict | None:
    item = await store.aget((user_id, "preferences"), "settings")
    return item.value if item else None

# Add memory for semantic search
async def add_user_memory(user_id: str, memory: str):
    ns = (user_id, "memory")
    await store.aput(ns, str(uuid.uuid4()), {
        "content": memory,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

# Search memories
async def search_user_memories(user_id: str, query: str):
    items = await store.asearch((user_id, "memory"), query=query, limit=5)
    return [item.value["content"] for item in items]
```

### Example 2: Cross-Project Query Workaround

```python
async def get_all_user_memories_across_projects(user_id: str, projects: list[str]):
    """Fetch user memories across multiple projects."""
    all_memories = []
    for project_id in projects:
        ns = (user_id, "projects", project_id, "memory")
        items = await store.asearch(ns, limit=100)
        all_memories.extend([item.value for item in items])
    return all_memories

async def save_cross_project_memory(user_id: str, memory: str, projects: list[str]):
    """Save memory for user in all projects."""
    key = str(uuid.uuid4())
    for project_id in projects:
        ns = (user_id, "projects", project_id, "memory")
        await store.aput(ns, key, {
            "content": memory,
            "shared": True  # Mark as cross-project
        })
```

### Example 3: Semantic Search with Embedding Index

```python
from langchain.embeddings import init_embeddings

# Configure embedding
embed_func = init_embeddings("openai:text-embedding-3-small")
store = AsyncPostgresStore(
    connection_string=DB_URL,
    index=IndexConfig(
        embed=embed_func,
        dims=1536,
        fields=["content"]  # Only embed "content" field
    )
)

# Store semantic memories
async def save_learning(user_id: str, topic: str, notes: str):
    ns = (user_id, "learning")
    await store.aput(ns, topic, {
        "content": notes,
        "topic": topic,
        "indexed": True
    })

# Find relevant learning by semantic similarity
async def find_relevant_learning(user_id: str, question: str):
    items = await store.asearch(
        (user_id, "learning"),
        query=question,
        limit=3
    )
    return [(item.key, item.value["content"]) for item in items]
```

---

## 11. Summary Table: Store Capabilities vs. Your Needs

| Need | Store Capability | Recommendation |
|------|------------------|-----------------|
| Store project sphere | ✅ Perfect | Use existing pattern: `("project", project_id, "sphere")` |
| Store user preferences | ✅ Excellent | Single key per namespace, atomic updates |
| Cross-project user memory | ⚠️ Limited | Semantic search works, but requires iteration for multi-project queries |
| Query user memory by semantic meaning | ✅ Yes | Configure embedding index, use `asearch(query=...)` |
| Hierarchical namespace queries | ❌ No | Manual iteration or denormalized index |
| Custom instructions per user | ✅ Good | Treat like Knowledge Sphere, separate namespace |
| Time-range filtering | ❌ No | Store timestamps in value, filter client-side |
| TTL/auto-cleanup | ⚠️ Partial | Manual cleanup or use LangSmith server TTL feature |
| Cross-namespace atomic updates | ❌ No | Accept eventual consistency or serialize manually |

---

## 12. Decision: Is Store Sufficient for Multi-Layer Memory?

**YES, with caveats:**

**Strengths:**
- Simple, reliable key-value semantics
- Good for namespace-isolated data (projects, users, categories)
- Semantic search is excellent for user memories
- Mature async API
- PostgreSQL backend is production-ready

**Weaknesses:**
- Cannot efficiently query across namespaces in single operation
- No range/time-based filtering
- Limited to exact-match or semantic search (no regex/fuzzy)

**Verdict for your architecture:**
- Use Store as primary backend for all memory layers ✅
- Accept manual iteration for cross-namespace queries (application layer)
- Build a separate index (Redis set, or database view) for cross-project discovery if needed
- Leverage semantic search for preference-less queries (e.g., "find learning notes about X")

---

## 13. Related Docs

- **Current Knowledge Sphere implementation**: `/doc/tech/knowledge-sphere.md`
- **Agent runtime & Store integration**: `/doc/tech/agent-runtime.md`
- **LangGraph persistence & memory**: LangChain official docs (oss/python/langgraph/persistence)
- **Project scope & architecture**: `/doc/vision.md`
