import { create } from "zustand";

interface StreamState {
  isStreaming: boolean;
  streamingText: string;
  activeTool: string | null;
  streamingChatId: string | null;
  startStream: (chatId: string) => void;
  appendText: (chunk: string) => void;
  setTool: (name: string | null) => void;
  endStream: () => void;
}

export const useStreamStore = create<StreamState>()((set) => ({
  isStreaming: false,
  streamingText: "",
  activeTool: null,
  streamingChatId: null,
  startStream: (chatId) =>
    set({
      isStreaming: true,
      streamingText: "",
      activeTool: null,
      streamingChatId: chatId,
    }),
  appendText: (chunk) =>
    set((s) => ({ streamingText: s.streamingText + chunk })),
  setTool: (name) => set({ activeTool: name }),
  endStream: () =>
    set({
      isStreaming: false,
      streamingText: "",
      activeTool: null,
      streamingChatId: null,
    }),
}));
