import type { Artifact, ArtifactDetail, ListResponse } from "./types";

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

const MOCK_ARTIFACT_DETAILS: Record<string, ArtifactDetail> = {
  "art-1": {
    id: "art-1",
    title: "CAP Theorem Summary",
    type: "markdown",
    thread_id: "chat-1a",
    created_at: "2025-12-15T14:30:00Z",
    content:
      "# CAP Theorem Summary\n\n## Overview\n\nThe CAP theorem (Brewer's theorem) states that any distributed data store can provide only two of the following three guarantees:\n\n| Property | Description |\n|----------|-------------|\n| **Consistency** | Every read receives the most recent write or an error |\n| **Availability** | Every request receives a non-error response |\n| **Partition Tolerance** | System continues despite network partitions |\n\n## Practical Implications\n\nSince network partitions are inevitable in distributed systems, the real choice is between **CP** and **AP**.\n\n```mermaid\ngraph TD\n    CAP[CAP Theorem] --> CP[CP: Consistency + Partition Tolerance]\n    CAP --> AP[AP: Availability + Partition Tolerance]\n    CP --> Ex1[ZooKeeper, HBase]\n    AP --> Ex2[Cassandra, DynamoDB]\n```",
  },
  "art-3": {
    id: "art-3",
    title: "Gradient Descent Cheat Sheet",
    type: "markdown",
    thread_id: "chat-2a",
    created_at: "2025-12-10T16:45:00Z",
    content:
      "# Gradient Descent Cheat Sheet\n\n## Update Rule\n\n$$\\theta_{t+1} = \\theta_t - \\alpha \\nabla J(\\theta_t)$$\n\n## Variants\n\n| Variant | Batch Size | Speed | Stability |\n|---------|-----------|-------|-----------|\n| Batch GD | Full dataset | Slow | Stable |\n| SGD | 1 sample | Fast | Noisy |\n| Mini-batch | 32-256 | Balanced | Balanced |\n\n## Learning Rate\n\nToo high → divergence, too low → slow convergence.\n\nCommon schedulers: step decay, cosine annealing, warm-up.",
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
  void projectId;
  return (
    MOCK_ARTIFACT_DETAILS[artifactId] ?? {
      id: artifactId,
      title: "Unknown artifact",
      type: "markdown",
      content: "",
      thread_id: "",
      created_at: new Date().toISOString(),
    }
  );
}

export async function downloadArtifact(
  projectId: string,
  artifactId: string,
  format: "md" | "pdf" = "md",
): Promise<void> {
  // TODO: window.open(`${apiClient.defaults.baseURL}/projects/${projectId}/artifacts/${artifactId}/download?format=${format}`)
  console.log(
    `[Mock] downloadArtifact: ${projectId}/${artifactId} format=${format}`,
  );
}
