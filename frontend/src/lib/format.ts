export function formatClock(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatWhen(value: string): string {
  const date = new Date(value);
  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${formatClock(value)}`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const minutes = Math.max(0, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function formatPercent(value: number | null): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function confidenceLabel(value: number): string {
  return `${Math.round(value * 100)}% investigation score`;
}
