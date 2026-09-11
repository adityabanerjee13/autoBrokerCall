import type { ReactNode } from "react";
import type { LeadType, SafetyVerdict, Temperature } from "../api/types";
import { titleCase } from "./format";

export function Pill({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <span className={`pill ${className}`}>{children}</span>;
}

export function LeadTypePill({ type }: { type: LeadType }) {
  return (
    <Pill
      className={
        type === "renter"
          ? "bg-agent/10 text-agent"
          : "bg-slate-200 text-slate-600"
      }
    >
      {type}
    </Pill>
  );
}

const LEAD_STATUS_STYLE: Record<string, string> = {
  New: "bg-slate-100 text-slate-600",
  Queued: "bg-slate-100 text-slate-600",
  Calling: "bg-agent/10 text-agent",
  Contacted: "bg-sky-100 text-sky-700",
  Qualified: "bg-emerald-100 text-emerald-700",
  "Appointment Set": "bg-emerald-100 text-emerald-700",
  Escalated: "bg-alarm/10 text-alarm",
  Closed: "bg-slate-200 text-slate-500",
  Unqualified: "bg-slate-200 text-slate-500",
};

export function LeadStatusPill({ status }: { status: string }) {
  return (
    <Pill className={LEAD_STATUS_STYLE[status] ?? "bg-slate-100 text-slate-600"}>
      {status}
    </Pill>
  );
}

const PROPERTY_STATUS_STYLE: Record<string, string> = {
  available: "bg-emerald-100 text-emerald-700",
  shown: "bg-sky-100 text-sky-700",
  under_offer: "bg-human/10 text-human",
  let: "bg-slate-200 text-slate-500",
  paused: "bg-slate-100 text-slate-500",
};

export function PropertyStatusPill({ status }: { status: string }) {
  return (
    <Pill className={PROPERTY_STATUS_STYLE[status] ?? "bg-slate-100 text-slate-600"}>
      {status.replace(/_/g, " ")}
    </Pill>
  );
}

export function AnalysisStatusPill({ status }: { status: string }) {
  const style =
    status === "done"
      ? "bg-judge/10 text-judge"
      : status === "failed"
        ? "bg-alarm/10 text-alarm"
        : "bg-slate-100 text-slate-500";
  return <Pill className={style}>analysis {status}</Pill>;
}

export function SafetyPill({ verdict }: { verdict: SafetyVerdict }) {
  const style =
    verdict === "fail"
      ? "bg-alarm text-white"
      : verdict === "warn"
        ? "bg-human/15 text-human"
        : "bg-emerald-100 text-emerald-700";
  return <Pill className={`${style} uppercase tracking-wide`}>{verdict}</Pill>;
}

export function TemperaturePill({ value }: { value: Temperature }) {
  const style =
    value === "hot"
      ? "bg-human/15 text-human"
      : value === "warm"
        ? "bg-sky-100 text-sky-700"
        : "bg-slate-100 text-slate-500";
  return <Pill className={style}>{value}</Pill>;
}

export function EscalationBadge({ reason }: { reason: string | null }) {
  if (!reason) return null;
  return (
    <Pill className="bg-alarm/10 font-mono text-[11px] text-alarm">
      {titleCase(reason.toLowerCase())}
    </Pill>
  );
}
