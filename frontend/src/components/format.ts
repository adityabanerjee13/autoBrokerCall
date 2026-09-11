// Presentation conventions, in one place so all three dashboards agree.
// Currency is always rupees with separators and a /mo suffix - every figure in
// this product is a monthly rent, and formatting one as a sale price would be a
// factual error, not a styling one.

export function rupees(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

export function rentPerMonth(amount: number): string {
  return `${rupees(amount)}/mo`;
}

export function rentRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  if (min !== null && max !== null)
    return `${rupees(min)}–${max.toLocaleString("en-IN")}/mo`;
  return rentPerMonth((min ?? max) as number);
}

/** m:ss */
export function duration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Relative under 24h, absolute beyond. */
export function when(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso);
  const mins = Math.floor((Date.now() - then.getTime()) / 60000);
  if (mins < 0) return absolute(then);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return absolute(then);
}

export function absolute(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function titleCase(snake: string): string {
  return snake.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
