import type { Artifact, ArtifactDetail, ListResponse } from "./types";
import { apiClient } from "./client";

// --- Mock data ---

const MOCK_ARTIFACTS: Record<string, Artifact[]> = {
  "proj-1": [
    {
      id: "art-1",
      title: "CAP Theorem Summary",
      type: "markdown",
      created_at: "2025-12-15T14:30:00Z",
    },
    {
      id: "art-2",
      title: "Consensus Algorithms Comparison",
      type: "markdown",
      created_at: "2025-12-14T11:00:00Z",
    },
  ],
  "proj-2": [
    {
      id: "art-3",
      title: "Gradient Descent Cheat Sheet",
      type: "markdown",
      created_at: "2025-12-10T16:45:00Z",
    },
  ],
};

const MOCK_ARTIFACT_DETAILS: Record<string, Record<string, ArtifactDetail>> = {
  "proj-1": {
    "art-1": {
      id: "art-1",
      title: "CAP Theorem Summary",
      type: "markdown",
      thread_id: "chat-1a",
      message_id: "msg-2",
      created_at: "2025-12-15T14:30:00Z",
      content:
        "# CAP Theorem Summary\n\n## Overview\n\nThe CAP theorem (Brewer's theorem) states that any distributed data store can provide only two of the following three guarantees:\n\n| Property | Description |\n|----------|-------------|\n| **Consistency** | Every read receives the most recent write or an error |\n| **Availability** | Every request receives a non-error response |\n| **Partition Tolerance** | System continues despite network partitions |\n\n## Practical Implications\n\nSince network partitions are inevitable in distributed systems, the real choice is between **CP** and **AP**.\n\n```mermaid\ngraph TD\n    CAP[CAP Theorem] --> CP[CP: Consistency + Partition Tolerance]\n    CAP --> AP[AP: Availability + Partition Tolerance]\n    CP --> Ex1[ZooKeeper, HBase]\n    AP --> Ex2[Cassandra, DynamoDB]\n```",
    },
    "art-2": {
      id: "art-2",
      title: "Consensus Algorithms Comparison",
      type: "markdown",
      thread_id: "chat-1a",
      message_id: "msg-4",
      created_at: "2025-12-14T11:00:00Z",
      content:
        "# Consensus Algorithms Comparison\n\n## Overview\n\nConsensus algorithms allow distributed systems to agree on a single value even in the presence of failures.\n\n## Raft vs Paxos\n\n| Feature | Raft | Paxos |\n|---------|------|-------|\n| **Understandability** | Designed for clarity | Notoriously complex |\n| **Leader election** | Explicit, term-based | Implicit via proposer |\n| **Log replication** | Append-only, leader-driven | Multi-decree, flexible |\n| **Membership changes** | Joint consensus | External reconfiguration |\n| **Industry adoption** | etcd, CockroachDB, TiKV | Chubby, Spanner |\n\n## Key Takeaway\n\nRaft is easier to implement and reason about. Paxos is more flexible but harder to get right in practice.",
    },
  },
  "proj-2": {
    "art-3": {
      id: "art-3",
      title: "Gradient Descent Cheat Sheet",
      type: "markdown",
      thread_id: "chat-2a",
      message_id: "msg-6",
      created_at: "2025-12-10T16:45:00Z",
      content:
        "# Gradient Descent Cheat Sheet\n\n## Update Rule\n\n$$\\theta_{t+1} = \\theta_t - \\alpha \\nabla J(\\theta_t)$$\n\n## Variants\n\n| Variant | Batch Size | Speed | Stability |\n|---------|-----------|-------|-----------|\n| Batch GD | Full dataset | Slow | Stable |\n| SGD | 1 sample | Fast | Noisy |\n| Mini-batch | 32-256 | Balanced | Balanced |\n\n## Learning Rate\n\nToo high → divergence, too low → slow convergence.\n\nCommon schedulers: step decay, cosine annealing, warm-up.",
    },
  },
};

// --- API functions ---

export async function getArtifacts(
  projectId: string,
): Promise<ListResponse<Artifact>> {
  // TODO: return (await apiClient.get(`/projects/${projectId}/artifacts`)).data
  return { items: MOCK_ARTIFACTS[projectId] ?? [] };
}

export async function getArtifact(
  projectId: string,
  artifactId: string,
): Promise<ArtifactDetail> {
  // TODO: return (await apiClient.get(`/projects/${projectId}/artifacts/${artifactId}`)).data
  return (
    MOCK_ARTIFACT_DETAILS[projectId]?.[artifactId] ?? {
      id: artifactId,
      title: "Unknown artifact",
      type: "markdown",
      content: "",
      thread_id: null,
      message_id: null,
      created_at: new Date().toISOString(),
    }
  );
}

export function downloadArtifact(
  projectId: string,
  artifactId: string,
  format: "md" | "pdf" = "md",
): void {
  window.open(
    `${apiClient.defaults.baseURL}/projects/${projectId}/artifacts/${artifactId}/download?format=${format}`,
  );
}
