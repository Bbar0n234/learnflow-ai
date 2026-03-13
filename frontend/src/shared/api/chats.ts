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
  void projectId;
  return {
    thread_id: crypto.randomUUID(),
    title: data.title ?? "New Chat",
    created_at: new Date().toISOString(),
  };
}

export async function getRecentChats(): Promise<ListResponse<RecentChat>> {
  // TODO: return (await apiClient.get("/chats/recent")).data
  return { items: MOCK_RECENT_CHATS };
}
