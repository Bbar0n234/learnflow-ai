import { useRef, useState, type DragEvent } from "react";

interface FileDropHandlers {
  onDragEnter: (e: DragEvent) => void;
  onDragOver: (e: DragEvent) => void;
  onDragLeave: (e: DragEvent) => void;
  onDrop: (e: DragEvent) => void;
}

/**
 * Drag&drop файлов на один контейнер (композер) — оверлей «Отпустите, чтобы
 * прикрепить» (мокап `mockups/attachments-artifacts.html`, блок 1). Счётчик
 * глубины (`depthRef`), а не булев флаг: `dragenter`/`dragleave` всплывают с
 * каждого вложенного узла контейнера (текстовое поле, чипы, кнопки), и без
 * счётчика `dragleave` с ребёнка гасил бы оверлей, пока курсор всё ещё над
 * композером — тот же приём, что в мокапе.
 */
export function useFileDrop(onFiles: (files: FileList) => void) {
  const [isDragging, setIsDragging] = useState(false);
  const depthRef = useRef(0);

  const dragHandlers: FileDropHandlers = {
    onDragEnter: (e) => {
      e.preventDefault();
      depthRef.current += 1;
      setIsDragging(true);
    },
    onDragOver: (e) => {
      e.preventDefault();
    },
    onDragLeave: (e) => {
      e.preventDefault();
      depthRef.current = Math.max(0, depthRef.current - 1);
      if (depthRef.current === 0) setIsDragging(false);
    },
    onDrop: (e) => {
      e.preventDefault();
      depthRef.current = 0;
      setIsDragging(false);
      if (e.dataTransfer?.files.length) onFiles(e.dataTransfer.files);
    },
  };

  return { isDragging, dragHandlers };
}
