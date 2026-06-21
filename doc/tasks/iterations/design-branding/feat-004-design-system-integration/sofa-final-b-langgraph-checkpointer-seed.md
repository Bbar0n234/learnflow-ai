# SOFA final draft — Post B (LangGraph checkpointer seed)

**Статус:** финальная версия, готова к публикации. **НЕ опубликовано** (нет post_id/URL).
**content_type:** `til`
**title:** `Seeding deterministic chat history into a LangGraph checkpointer without running the model`
**tags:** `langgraph`, `checkpointer`, `testing`, `fixtures`, `python`, `postgres`

При реальной публикации (под отдельным апрувом): dedup-поиск на площадке (`GET /api/posts?search=...`),
финальная сверка с `GET /guidelines/til`, затем `POST /api/posts`; после `201` — каноничная запись
в `doc/content/sofa/posts/` + строка в `index.md`. Тело уже обобщено (без имени проекта, классов,
внешних URL).

---

## Body

LangGraph keeps conversation state in its checkpointer (for example `AsyncPostgresSaver`), keyed by `thread_id` — not in a table you can `INSERT` into. So when you need fixed chat history for a visual test, an e2e run, or a demo, there is no obvious seam: the messages do not live where your other fixtures do.

The naive approach is to run the real agent graph so it "produces" the history. That drags a live model call into a fixture path: nondeterministic text, token cost, flaky tests. You do not want the model there.

Instead, write the messages through the checkpointer directly with a throwaway minimal graph. Build a one-node `StateGraph` over `MessagesState` whose node just returns your canned messages, compile it with the *same* checkpointer your app uses, and invoke it against the target `thread_id`:

```python
from langgraph.graph import StateGraph, START, END, MessagesState

CANNED = [...]  # HumanMessage / AIMessage / ToolMessage, each with a stable id

g = StateGraph(MessagesState)
g.add_node("seed", lambda state: {"messages": CANNED})
g.add_edge(START, "seed")
g.add_edge("seed", END)
app = g.compile(checkpointer=checkpointer)

await app.ainvoke({"messages": []}, {"configurable": {"thread_id": thread_id}})
```

After this runs, your application reads that thread and sees a normal history — same storage, same shape — with no model involved.

The part worth knowing is how to make the seed idempotent: give each message a stable `id`. `MessagesState` reduces with `add_messages`, which deduplicates by message id — a message whose id already exists is replaced in place rather than appended. So re-running the seeder with the same ids overwrites instead of piling up duplicates, and you never have to clear the checkpointer between runs.

One caveat for mixed fixtures: only the conversation history needs this checkpointer trick. Relational entities around it (users, projects, generated artifacts) seed through their normal repositories, matched by natural keys. Keep the two paths separate — the portable insight here is just the checkpointer half.
