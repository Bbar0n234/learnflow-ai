type LogLevel = "debug" | "info" | "warn" | "error";

const LEVELS: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const MIN_LEVEL: LogLevel = import.meta.env.DEV ? "debug" : "warn";

function shouldLog(level: LogLevel): boolean {
  return LEVELS[level] >= LEVELS[MIN_LEVEL];
}

export const logger = {
  debug: (...args: unknown[]) => shouldLog("debug") && console.debug(...args),
  info: (...args: unknown[]) => shouldLog("info") && console.info(...args),
  warn: (...args: unknown[]) => shouldLog("warn") && console.warn(...args),
  error: (...args: unknown[]) => shouldLog("error") && console.error(...args),
};
