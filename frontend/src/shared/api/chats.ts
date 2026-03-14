// TODO: import { apiClient } from "./client";
import type {
  Chat,
  ChatCreateResponse,
  ChatDetail,
  CreateChatRequest,
  ListResponse,
  RecentChat,
} from "./types";

// --- Mock data ---

const MOCK_CHATS: Record<string, Chat[]> = {
  "proj-1": [
    {
      thread_id: "chat-1a",
      title: "CAP theorem deep dive",
      created_at: "2025-12-10T10:00:00Z",
      updated_at: "2025-12-15T14:30:00Z",
    },
    {
      thread_id: "chat-1b",
      title: "Consensus algorithms overview",
      created_at: "2025-12-12T09:00:00Z",
      updated_at: "2025-12-14T11:00:00Z",
    },
  ],
  "proj-2": [
    {
      thread_id: "chat-2a",
      title: "Gradient descent explanation",
      created_at: "2025-12-08T15:00:00Z",
      updated_at: "2025-12-10T16:45:00Z",
    },
    {
      thread_id: "chat-2b",
      title: "Neural network architectures",
      created_at: "2025-12-09T10:00:00Z",
      updated_at: "2025-12-09T12:00:00Z",
    },
    {
      thread_id: "chat-2c",
      title: "Overfitting and regularization",
      created_at: "2025-12-10T08:00:00Z",
      updated_at: "2025-12-10T10:30:00Z",
    },
  ],
  "proj-3": [
    {
      thread_id: "chat-3a",
      title: "REST vs GraphQL",
      created_at: "2025-12-13T14:00:00Z",
      updated_at: "2025-12-14T12:00:00Z",
    },
  ],
};

const MOCK_CHAT_DETAIL: Record<string, ChatDetail> = {
  "chat-1a": {
    thread_id: "chat-1a",
    title: "CAP theorem deep dive",
    messages: [
      {
        id: "msg-1",
        role: "user",
        content: "Explain the CAP theorem in simple terms",
        created_at: "2025-12-15T14:00:00Z",
      },
      {
        id: "msg-2",
        role: "assistant",
        content:
          "## CAP Theorem\n\nThe CAP theorem states that a distributed system can only guarantee **two out of three** properties simultaneously:\n\n- **Consistency** — every read receives the most recent write\n- **Availability** — every request receives a response\n- **Partition Tolerance** — the system continues to operate despite network partitions\n\n```typescript\ntype CAPChoice = \n  | 'CP' // Consistency + Partition Tolerance\n  | 'AP' // Availability + Partition Tolerance\n  | 'CA' // Consistency + Availability (no partitions)\n```\n\nIn practice, since network partitions are unavoidable, you're really choosing between **CP** and **AP** systems.",
        created_at: "2025-12-15T14:01:00Z",
      },
      {
        id: "msg-3",
        role: "user",
        content: "Give me real-world examples of CP and AP systems",
        created_at: "2025-12-15T14:05:00Z",
      },
      {
        id: "msg-4",
        role: "assistant",
        content:
          "### CP Systems (Consistency + Partition Tolerance)\n\n- **ZooKeeper** — leader-based, rejects writes during partition\n- **HBase** — strong consistency, may become unavailable\n- **MongoDB** (with majority write concern)\n\n### AP Systems (Availability + Partition Tolerance)\n\n- **Cassandra** — always writable, eventual consistency\n- **DynamoDB** — high availability, configurable consistency\n- **CouchDB** — multi-master replication\n\n> $E = mc^2$ — just kidding, but math rendering works too!\n\n```mermaid\ngraph LR\n    CP[CP Systems] --> ZK[ZooKeeper]\n    CP --> HB[HBase]\n    AP[AP Systems] --> CS[Cassandra]\n    AP --> DDB[DynamoDB]\n```",
        created_at: "2025-12-15T14:06:00Z",
      },
    ],
  },
  "chat-2a": {
    thread_id: "chat-2a",
    title: "Gradient descent explanation",
    messages: [
      {
        id: "msg-5",
        role: "user",
        content: "How does gradient descent work?",
        created_at: "2025-12-10T15:00:00Z",
      },
      {
        id: "msg-6",
        role: "assistant",
        content:
          "## Gradient Descent\n\nGradient descent is an optimization algorithm that iteratively adjusts parameters to minimize a loss function.\n\n### The Update Rule\n\n$$\\theta_{t+1} = \\theta_t - \\alpha \\nabla J(\\theta_t)$$\n\nWhere:\n- $\\theta$ — model parameters\n- $\\alpha$ — learning rate\n- $\\nabla J(\\theta)$ — gradient of the loss function\n\n```python\ndef gradient_descent(gradient_fn, init_params, lr=0.01, steps=100):\n    params = init_params\n    for _ in range(steps):\n        grad = gradient_fn(params)\n        params = params - lr * grad\n    return params\n```\n\nThe key intuition: move in the **opposite direction** of the gradient (steepest descent).",
        created_at: "2025-12-10T15:01:00Z",
      },
    ],
  },
};

const MOCK_RECENT_CHATS: RecentChat[] = [
  {
    thread_id: "chat-1a",
    title: "CAP theorem deep dive",
    project_id: "proj-1",
    project_name: "Distributed Systems Lecture",
    updated_at: "2025-12-15T14:30:00Z",
  },
  {
    thread_id: "chat-2a",
    title: "Gradient descent explanation",
    project_id: "proj-2",
    project_name: "ML Fundamentals Workshop",
    updated_at: "2025-12-10T16:45:00Z",
  },
  {
    thread_id: "chat-3a",
    title: "REST vs GraphQL",
    project_id: "proj-3",
    project_name: "API Design Best Practices",
    updated_at: "2025-12-14T12:00:00Z",
  },
];

// --- API functions ---

export async function getChats(projectId: string): Promise<ListResponse<Chat>> {
  // TODO: return (await apiClient.get(`/projects/${projectId}/chats`)).data
  return { items: MOCK_CHATS[projectId] ?? [] };
}

export async function getChat(
  projectId: string,
  chatId: string,
): Promise<ChatDetail> {
  // TODO: return (await apiClient.get(`/projects/${projectId}/chats/${chatId}`)).data
  void projectId;
  return (
    MOCK_CHAT_DETAIL[chatId] ?? {
      thread_id: chatId,
      title: "Unknown chat",
      messages: [],
    }
  );
}

export async function createChat(
  projectId: string,
  data: CreateChatRequest,
): Promise<ChatCreateResponse> {
  // TODO: return (await apiClient.post(`/projects/${projectId}/chats`, data)).data
  const now = new Date().toISOString();
  const chat: Chat = {
    thread_id: crypto.randomUUID(),
    title: data.title ?? "New Chat",
    created_at: now,
    updated_at: now,
  };
  if (!MOCK_CHATS[projectId]) {
    MOCK_CHATS[projectId] = [];
  }
  MOCK_CHATS[projectId].push(chat);
  return {
    thread_id: chat.thread_id,
    title: chat.title,
    created_at: chat.created_at,
  };
}

export async function getRecentChats(): Promise<ListResponse<RecentChat>> {
  // TODO: return (await apiClient.get("/chats/recent")).data
  return { items: MOCK_RECENT_CHATS };
}

// --- Cancel ---

const cancelledChats = new Set<string>();

export async function cancelChat(
  projectId: string,
  chatId: string,
): Promise<{ ok: true }> {
  // TODO: return (await apiClient.post(`/projects/${projectId}/chats/${chatId}/cancel`)).data
  void projectId;
  cancelledChats.add(chatId);
  return { ok: true };
}

// --- Mock SSE streaming ---

const MOCK_RESPONSE_TEXT = `## Ответ агента

Вот что я нашёл по вашему вопросу:

1. **Первый пункт** — базовое объяснение концепции
2. **Второй пункт** — практические примеры

\`\`\`typescript
function example() {
  return "Hello from agent!";
}
\`\`\`

Надеюсь, это помогло! Давайте разберём подробнее.`;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function encodeSSE(data: object): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(data)}\n\n`);
}

export function mockSendMessage(
  projectId: string,
  chatId: string,
  content: string,
  abortSignal?: AbortSignal,
): ReadableStream<Uint8Array> {
  // Ensure MOCK_CHAT_DETAIL entry exists
  if (!MOCK_CHAT_DETAIL[chatId]) {
    const chatEntry = Object.values(MOCK_CHATS)
      .flat()
      .find((c) => c.thread_id === chatId);
    MOCK_CHAT_DETAIL[chatId] = {
      thread_id: chatId,
      title: chatEntry?.title ?? "New Chat",
      messages: [],
    };
  }

  // Add user message
  const userMsg = {
    id: crypto.randomUUID(),
    role: "user" as const,
    content,
    created_at: new Date().toISOString(),
  };
  MOCK_CHAT_DETAIL[chatId].messages.push(userMsg);

  // Clear cancel flag
  cancelledChats.delete(chatId);

  void projectId;

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const chunks = MOCK_RESPONSE_TEXT.match(/.{1,30}/gs) ?? [];

      // Phase 1: first half of text chunks
      const midpoint = Math.ceil(chunks.length / 2);
      for (let i = 0; i < midpoint; i++) {
        if (abortSignal?.aborted) {
          controller.close();
          return;
        }
        if (cancelledChats.has(chatId)) {
          controller.enqueue(
            encodeSSE({ type: "error", detail: "Generation cancelled" }),
          );
          cancelledChats.delete(chatId);
          controller.close();
          return;
        }
        controller.enqueue(
          encodeSSE({ type: "text_chunk", content: chunks[i] }),
        );
        await delay(100);
      }

      // Phase 2: tool use
      if (abortSignal?.aborted) {
        controller.close();
        return;
      }
      if (cancelledChats.has(chatId)) {
        controller.enqueue(
          encodeSSE({ type: "error", detail: "Generation cancelled" }),
        );
        cancelledChats.delete(chatId);
        controller.close();
        return;
      }
      controller.enqueue(
        encodeSSE({
          type: "tool_start",
          tool: "knowledge_search",
          call_id: "call-1",
        }),
      );
      await delay(1500);

      if (abortSignal?.aborted) {
        controller.close();
        return;
      }
      if (cancelledChats.has(chatId)) {
        controller.enqueue(
          encodeSSE({ type: "error", detail: "Generation cancelled" }),
        );
        cancelledChats.delete(chatId);
        controller.close();
        return;
      }
      controller.enqueue(
        encodeSSE({
          type: "tool_end",
          tool: "knowledge_search",
          call_id: "call-1",
        }),
      );

      // Phase 3: remaining text chunks
      for (let i = midpoint; i < chunks.length; i++) {
        if (abortSignal?.aborted) {
          controller.close();
          return;
        }
        if (cancelledChats.has(chatId)) {
          controller.enqueue(
            encodeSSE({ type: "error", detail: "Generation cancelled" }),
          );
          cancelledChats.delete(chatId);
          controller.close();
          return;
        }
        controller.enqueue(
          encodeSSE({ type: "text_chunk", content: chunks[i] }),
        );
        await delay(100);
      }

      // Phase 4: artifact
      if (abortSignal?.aborted) {
        controller.close();
        return;
      }
      if (cancelledChats.has(chatId)) {
        controller.enqueue(
          encodeSSE({ type: "error", detail: "Generation cancelled" }),
        );
        cancelledChats.delete(chatId);
        controller.close();
        return;
      }
      controller.enqueue(
        encodeSSE({
          type: "artifact_created",
          id: crypto.randomUUID(),
          title: "Конспект по теме",
          artifact_type: "note",
        }),
      );
      await delay(500);

      // Phase 5: done
      const assistantMsg = {
        id: crypto.randomUUID(),
        role: "assistant" as const,
        content: MOCK_RESPONSE_TEXT,
        created_at: new Date().toISOString(),
      };
      MOCK_CHAT_DETAIL[chatId]!.messages.push(assistantMsg);

      controller.enqueue(
        encodeSSE({ type: "done", message_id: assistantMsg.id }),
      );
      controller.close();
    },
  });
}
