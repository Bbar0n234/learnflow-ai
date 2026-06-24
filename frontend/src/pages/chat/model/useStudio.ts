import { useState } from "react";

export type StudioTab = "sphere" | "artifacts";

export function useStudio() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<StudioTab>("sphere");
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(
    null,
  );
  const [lensOpen, setLensOpen] = useState(false);

  return {
    open,
    tab,
    selectedArtifactId,
    lensOpen,
    toggle: () => setOpen((v) => !v),
    setTab,
    setSelectedArtifactId,
    setLensOpen,
    close: () => setOpen(false),
  };
}

export type StudioControls = ReturnType<typeof useStudio>;
