import { useState } from "react";

export interface ComposerAttachment {
  id: string;
  file: File;
}

/**
 * Состояние прикреплённых, но ещё не отправленных файлов композера
 * (design-brief § Вложения пользователя, § Тайминг): чисто клиентское — до
 * отправки ничего не уходит на сервер, а ✕ выбрасывает файл без единого
 * запроса. `id` — не имя файла: два выбранных файла с одинаковым именем
 * должны оставаться независимо убираемыми чипами.
 *
 * Переиспользуется между `ChatInput` (композер существующего чата и,
 * транзитивно, `ChatDraft`, `pages/chat`) и полем первого сообщения
 * (`pages/project-chats/ui/ChatList.tsx`) — общая точка обязана жить в
 * `shared`, потому что кросс-импорт между слайсами одного слоя `pages`
 * запрещён FSD-границами (`eslint.config.mjs` § boundaries/dependencies).
 */
export function useComposerAttachments() {
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);

  function addFiles(fileList: FileList | File[]) {
    const next = Array.from(fileList).map((file) => ({
      id: crypto.randomUUID(),
      file,
    }));
    if (next.length === 0) return;
    setAttachments((prev) => [...prev, ...next]);
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => prev.filter((attachment) => attachment.id !== id));
  }

  function clear() {
    setAttachments([]);
  }

  return { attachments, addFiles, removeAttachment, clear };
}

/**
 * Б/КБ/МБ для подписи размера на чипе композера (мокап
 * `mockups/attachments-artifacts.html`, блок 1). Чип истории размера не
 * показывает вовсе (контракт `MessageOut` его не отдаёт, OQ-4 плана T2) —
 * это единственный потребитель.
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} МБ`;
}
