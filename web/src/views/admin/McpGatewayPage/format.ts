export const PAGE_SIZE = 20;

const NBSP = "\u00A0";

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value}${NBSP}B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(1)}${NBSP}${units[unit]}`;
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}${NBSP}ms`;
  const seconds = ms / 1000;
  if (seconds < 10) return `${seconds.toFixed(1)}${NBSP}s`;
  return `${Math.round(seconds)}${NBSP}s`;
}

export function errorMessage(error: Error | unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
