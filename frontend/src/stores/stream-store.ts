import { create } from "zustand";

export interface StreamingArtifact {
  id: string;
  title: string;
  artifact_type: string;
}

interface StreamState {
  isStreaming: boolean;
  streamingText: string;
  activeTool: string | null;
  streamingChatId: string | null;
  streamingArtifacts: StreamingArtifact[];
  startStream: (chatId: string) => void;
  appendText: (chunk: string) => void;
  setTool: (name: string | null) => void;
  addArtifact: (artifact: StreamingArtifact) => void;
  endStream: () => void;
}

export const useStreamStore = create<StreamState>()((set) => ({
  isStreaming: false,
  streamingText: "",
  activeTool: null,
  streamingChatId: null,
  streamingArtifacts: [],
  startStream: (chatId) =>
    set({
      isStreaming: true,
      streamingText: "",
      activeTool: null,
      streamingChatId: chatId,
      streamingArtifacts: [],
    }),
  appendText: (chunk) =>
    set((s) => ({ streamingText: s.streamingText + chunk })),
  setTool: (name) => set({ activeTool: name }),
  addArtifact: (artifact) =>
    set((s) => ({ streamingArtifacts: [...s.streamingArtifacts, artifact] })),
  endStream: () =>
    set({
      isStreaming: false,
      streamingText: "",
      activeTool: null,
      streamingChatId: null,
      streamingArtifacts: [],
    }),
}));
