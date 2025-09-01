export type ExportFormat = 'markdown' | 'pdf';
export type ExportMode = 'single' | 'package';
export type PackageType = 'final' | 'all';

export interface ExportContext {
  threadId: string;
  sessionId: string;
  availableDocuments: string[];
}