import { create } from "zustand";

export interface StreamingArtifact {
  id: string;
  title: string;
  type: string;
}

interface StreamState {
  isStreaming: boolean;
  streamingText: string;
  activeTool: string | null;
  streamingChatId: string | null;
  streamingArtifacts: StreamingArtifact[];
  redacted: boolean;
  isReviewing: boolean;
  startStream: (chatId: string) => void;
  appendText: (chunk: string) => void;
  setTool: (name: string | null) => void;
  addArtifact: (artifact: StreamingArtifact) => void;
  replaceWithRedacted: (text: string) => void;
  setReviewing: (value: boolean) => void;
  endStream: () => void;
}

export const useStreamStore = create<StreamState>()((set) => ({
  isStreaming: false,
  streamingText: "",
  activeTool: null,
  streamingChatId: null,
  streamingArtifacts: [],
  redacted: false,
  isReviewing: false,
  startStream: (chatId) =>
    set({
      isStreaming: true,
      streamingText: "",
      activeTool: null,
      streamingChatId: chatId,
      streamingArtifacts: [],
      redacted: false,
      isReviewing: false,
    }),
  appendText: (chunk) =>
    set((s) => (s.redacted ? s : { streamingText: s.streamingText + chunk })),
  setTool: (name) => set({ activeTool: name }),
  addArtifact: (artifact) =>
    set((s) => ({ streamingArtifacts: [...s.streamingArtifacts, artifact] })),
  replaceWithRedacted: (text) =>
    set({
      streamingText: text,
      redacted: true,
      activeTool: null,
      isReviewing: false,
    }),
  setReviewing: (value) => set({ isReviewing: value }),
  endStream: () =>
    set({
      isStreaming: false,
      streamingText: "",
      activeTool: null,
      streamingChatId: null,
      streamingArtifacts: [],
      redacted: false,
      isReviewing: false,
    }),
}));
