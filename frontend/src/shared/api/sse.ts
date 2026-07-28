// События SSE-протокола агент-стрима. Спецификация — doc/tech/streaming.md.
export type SSEEvent =
  | { type: "text_chunk"; content: string }
  | { type: "tool_start"; tool: string; call_id: string }
  | { type: "tool_end"; tool: string; call_id: string }
  | {
      type: "artifact_created";
      id: string;
      title: string;
      artifact_type: string;
    }
  | { type: "done"; message_id?: string; trace_id?: string }
  | { type: "title_updated"; title: string }
  | { type: "error"; detail: string }
  | { type: "security_block"; reason: string }
  | { type: "final_output_review_started" }
  | { type: "final_output_review_complete" };
