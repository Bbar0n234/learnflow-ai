import type { Sphere, UpdateSphereRequest } from "./types";

// --- Mock data ---

const MOCK_SPHERE: Record<string, Sphere> = {
  "proj-1": {
    project_id: "proj-1",
    content:
      "## Distributed Systems\n\n### Key Concepts\n\n- **CAP Theorem** — consistency, availability, partition tolerance trade-off\n- **Consensus** — Raft, Paxos algorithms for agreement\n- **Replication** — leader-follower, multi-leader, leaderless strategies\n\n### Open Questions\n\n- How does CRDTs compare to consensus-based approaches?\n- What are the practical limits of eventual consistency?",
    updated_at: "2025-12-15T14:30:00Z",
  },
  "proj-2": {
    project_id: "proj-2",
    content:
      "## ML Fundamentals\n\n### Topics Covered\n\n- Gradient descent and variants (SGD, Adam)\n- Neural network basics\n- Overfitting, regularization (L1, L2, dropout)\n\n### Key Formulas\n\n$$L = -\\frac{1}{N}\\sum_{i=1}^{N} y_i \\log(\\hat{y}_i)$$",
    updated_at: "2025-12-10T16:45:00Z",
  },
};

// --- API functions ---

export async function getSphere(projectId: string): Promise<Sphere> {
  // TODO: return (await apiClient.get(`/projects/${projectId}/sphere`)).data
  return (
    MOCK_SPHERE[projectId] ?? {
      project_id: projectId,
      content: "",
      updated_at: new Date().toISOString(),
    }
  );
}

export async function updateSphere(
  projectId: string,
  data: UpdateSphereRequest,
): Promise<Sphere> {
  // TODO: return (await apiClient.put(`/projects/${projectId}/sphere`, data)).data
  const updated: Sphere = {
    project_id: projectId,
    content: data.content,
    updated_at: new Date().toISOString(),
  };
  MOCK_SPHERE[projectId] = updated;
  return updated;
}
