import { apiClient } from "./client";

export async function submitFeedback(
  traceId: string,
  score: boolean | null,
): Promise<void> {
  await apiClient.post("/feedback", { trace_id: traceId, score });
}
