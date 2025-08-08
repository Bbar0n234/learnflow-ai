export const API_BASE_URL = '/api';

export const SUPPORTED_FILE_TYPES = {
  MARKDOWN: 'text/markdown',
  TEXT: 'text/plain',
  JSON: 'application/json',
} as const;

export const FILE_EXTENSIONS = {
  MARKDOWN: ['.md', '.markdown'],
  TEXT: ['.txt'],
  JSON: ['.json'],
} as const;

export const DEBOUNCE_DELAY = 300; // ms

export const THEME_STORAGE_KEY = 'learnflow-theme';

export const ERROR_MESSAGES = {
  NETWORK_ERROR: 'Network error. Please check your connection.',
  SERVER_ERROR: 'Server error. Please try again later.',
  NOT_FOUND: 'Resource not found.',
  UNAUTHORIZED: 'Unauthorized access.',
  GENERIC: 'An unexpected error occurred.',
} as const;