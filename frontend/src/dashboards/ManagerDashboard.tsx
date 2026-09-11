import { useMemo, useState } from "react";
import { useAnalysis, useManagerStats } from "../api/hooks";
import type { AnalysisRow } from "../api/types";
import ActiveCallPanel from "../components/ActiveCallPanel";
import AddLeadForm from "../components/AddLeadForm";
import CallDrawer from "../components/CallDrawer";
import CompletedCalls from "../components/CompletedCalls";
import LeadQueue from "../components/LeadQueue";
import { duration, when } from "../components/format";
import { SafetyPill, TemperaturePill } from "../components/Pills";

type SortKey = "conversion" | "safety";

// Conversion and safety are sorted independently and never combined. There is
// no blended column here on purpose: a call can convert well and still be a
// compliance failure, and one number would hide exactly that case.
const SAFETY_ORDER: Record<string, number> = { fail: 0, warn: 1, pass: 2 };

export default function ManagerDashboard() {
  const { data: stats } = useManagerStats();
  const { data: rows } = useAnalysis();
  const [sort, setSort] = useState<SortKey>("conversion");
  const [openCall, setOpenCall] = useState<string | null>(null);
  const [addingLead, setAddingLead] = useState(false);

  const sorted = useMemo(() => {
    const list = [...(rows ?? [])];
    if (sort === "conversion") {
      list.sort((a, b) => b.conversion_score - a.conversion_score);
    } else {
      list.sort(
        (a, b) =>
          SAFETY_ORDER[a.safety_verdict] - SAFETY_ORDER[b.safety_verdict] ||
          b.violation_count - a.violation_count
      );
    }
    return list;
  }, [rows, sort]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Operations</h1>
        <button className="btn-primary" onClick={() => setAddingLead(true)}>
          + Add lead
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Tile label="Calls today" value={stats ? String(stats.calls_today) : "—"} />
        <Tile
          label="Escalation rate"
          value={stats ? `${Math.round(stats.escalation_rate * 100)}%` : "—"}
          tone={stats && stats.escalation_rate > 0.3 ? "text-human" : undefined}
        />
        <Tile
          label="Safety fails"
          value={stats ? String(stats.safety_fails) : "—"}
          tone={stats && stats.safety_fails > 0 ? "text-alarm" : undefined}
        />
        <Tile
          label="Avg completeness"
          value={stats ? `${Math.round(stats.avg_completeness * 100)}%` : "—"}
        />
        <Tile
          label="Avg talk ratio"
          value={stats ? `${Math.round(stats.avg_talk_ratio * 100)}%` : "—"}
        />
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Call analysis</h2>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            Sort by
            <button
              onClick={() => setSort("conversion")}
              className={`rounded px-2 py-1 ${
                sort === "conversion"
                  ? "bg-judge/10 font-medium text-judge"
                  : "hover:bg-slate-100"
              }`}
            >
              Conversion
            </button>
            <button
              onClick={() => setSort("safety")}
              className={`rounded px-2 py-1 ${
                sort === "safety"
                  ? "bg-judge/10 font-medium text-judge"
                  : "hover:bg-slate-100"
              }`}
            >
              Safety
            </button>
          </div>
        </div>

        {!sorted.length ? (
          <p className="empty">No analysed calls yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-100">
                <tr>
                  <th className="th">Call</th>
                  <th className="th">Lead</th>
                  <th className="th">Duration</th>
                  <th className="th">Conversion</th>
                  <th className="th">Safety</th>
                  <th className="th">Escalated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sorted.map((row) => (
                  <tr
                    key={row.call_id}
                    onClick={() => setOpenCall(row.call_id)}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <td className="td font-mono text-xs text-slate-600">
                      {row.call_id}
                      <div className="text-[11px] text-slate-400">
                        {when(row.ended_at)}
                      </div>
                    </td>
                    <td className="td text-slate-800">{row.lead_name}</td>
                    <td className="td font-mono text-slate-600">
                      {duration(row.duration_s)}
                    </td>
                    <td className="td">
                      <ConversionCell row={row} />
                    </td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <SafetyPill verdict={row.safety_verdict} />
                        {row.violation_count > 0 && (
                          <span className="text-xs text-slate-500">
                            {row.violation_count} violation
                            {row.violation_count === 1 ? "" : "s"}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="td text-slate-600">
                      {row.escalated ? "yes" : "no"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <LeadQueue readOnly />
      <ActiveCallPanel />
      <CompletedCalls readOnly />

      <CallDrawer callId={openCall} onClose={() => setOpenCall(null)} />
      {addingLead && <AddLeadForm onClose={() => setAddingLead(false)} />}
    </div>
  );
}

function ConversionCell({ row }: { row: AnalysisRow }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-judge"
          style={{ width: `${Math.round(row.conversion_score * 100)}%` }}
        />
      </div>
      <span className="w-8 font-mono text-xs tabular-nums text-slate-700">
        {row.conversion_score.toFixed(2)}
      </span>
      <TemperaturePill value={row.lead_temperature} />
    </div>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="panel px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tone ?? "text-slate-900"}`}>
        {value}
      </div>
    </div>
  );
}
