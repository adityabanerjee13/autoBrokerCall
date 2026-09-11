import { useCall } from "../api/hooks";
import type { CallDetail } from "../api/types";
import { duration, titleCase } from "./format";
import { SafetyPill, TemperaturePill } from "./Pills";

type Violation = NonNullable<CallDetail["analysis"]["safety"]>["violations"][number];

export default function CallDrawer({
  callId,
  onClose,
}: {
  callId: string | null;
  onClose: () => void;
}) {
  const { data: call, isLoading } = useCall(callId);
  if (!callId) return null;

  const conversion = call?.analysis.conversion;
  const safety = call?.analysis.safety;

  // Turn index -> the violations the safety judge raised against it, so the
  // quote and the explanation sit next to the line they are about.
  const flagged = new Map<number, Violation[]>();
  for (const v of safety?.violations ?? []) {
    flagged.set(v.turn, [...(flagged.get(v.turn) ?? []), v]);
  }

  return (
    <div className="fixed inset-0 z-30 flex justify-end">
      <button
        aria-label="Close"
        className="flex-1 bg-slate-900/20"
        onClick={onClose}
      />
      <aside className="flex w-full max-w-2xl flex-col overflow-y-auto border-l border-slate-200 bg-white shadow-xl">
        <header className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
          <div>
            <div className="font-mono text-sm text-slate-700">{callId}</div>
            {call?.lead && (
              <div className="text-xs text-slate-500">
                {call.lead.first_name} {call.lead.last_name} · {call.lead.lead_type}
              </div>
            )}
          </div>
          <button className="btn-ghost" onClick={onClose}>
            Close
          </button>
        </header>

        {isLoading || !call ? (
          <p className="empty">Loading…</p>
        ) : (
          <div className="space-y-5 p-5">
            <div className="grid grid-cols-4 gap-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-center">
              <Metric label="Duration" value={duration(call.duration_s ?? 0)} />
              <Metric
                label="Talk ratio"
                value={`${Math.round(call.metrics.agent_talk_ratio * 100)}%`}
              />
              <Metric label="Avg latency" value={`${call.metrics.avg_latency_ms}ms`} />
              <Metric label="Dead air" value={String(call.metrics.dead_air_events)} />
            </div>

            {call.escalated && (
              <div className="rounded-md border border-alarm/30 bg-alarm/10 px-3 py-2 text-sm font-medium text-alarm">
                Escalated · {titleCase((call.escalation_reason ?? "").toLowerCase())}
              </div>
            )}

            <div className="grid gap-3 md:grid-cols-2">
              <section className="rounded-md border border-slate-200 p-3">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-judge">
                  Conversion
                </h3>
                {conversion ? (
                  <dl className="space-y-1.5 text-sm">
                    <Row label="Track score" value={conversion.track_score.toFixed(2)} />
                    <Row
                      label="Completeness"
                      value={`${Math.round(conversion.completeness * 100)}%`}
                    />
                    <Row
                      label="Next step"
                      value={conversion.next_step ?? (conversion.next_step_secured ? "secured" : "none")}
                    />
                    <div className="flex items-center gap-2 pt-1">
                      <span className="text-xs text-slate-500">Temperature</span>
                      <TemperaturePill value={conversion.lead_temperature} />
                    </div>
                    {conversion.objection_handling && (
                      <p className="pt-2 text-xs text-slate-500">
                        Objections {conversion.objection_handling.score}/5 —{" "}
                        {conversion.objection_handling.rationale}
                      </p>
                    )}
                    {conversion.fields_missing.length > 0 && (
                      <p className="pt-1 text-xs text-human">
                        Missing: {conversion.fields_missing.join(", ")}
                      </p>
                    )}
                  </dl>
                ) : (
                  <p className="text-sm text-slate-400">Not graded.</p>
                )}
              </section>

              <section className="rounded-md border border-slate-200 p-3">
                <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-judge">
                  Safety
                  {safety && <SafetyPill verdict={safety.verdict} />}
                </h3>
                {safety ? (
                  <div className="space-y-1.5 text-sm">
                    <Row
                      label="Should have escalated"
                      value={safety.escalation.should_have ? "yes" : "no"}
                    />
                    <Row label="Did escalate" value={safety.escalation.did ? "yes" : "no"} />
                    {safety.escalation.miss_type && (
                      <Row label="Miss type" value={safety.escalation.miss_type} />
                    )}
                    {safety.pressure_flags.length > 0 && (
                      <p className="pt-1 text-xs text-human">
                        Pressure: {safety.pressure_flags.join(", ")}
                      </p>
                    )}
                    {safety.unverified_claims.length > 0 && (
                      <p className="pt-1 text-xs text-alarm">
                        {safety.unverified_claims.length} unverified claim
                        {safety.unverified_claims.length === 1 ? "" : "s"}
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-slate-400">Not graded.</p>
                )}
              </section>
            </div>

            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Transcript
              </h3>
              <div className="space-y-2">
                {call.transcript.map((turn) => {
                  const violations = flagged.get(turn.idx) ?? [];
                  const isFlagged = violations.length > 0;
                  return (
                    <div key={turn.idx}>
                      <div
                        className={`rounded-md px-3 py-2 text-sm ${
                          isFlagged
                            ? "border border-alarm/40 bg-alarm/5"
                            : turn.role === "agent"
                              ? "bg-slate-50 text-slate-600"
                              : "bg-white ring-1 ring-slate-200"
                        }`}
                      >
                        <span className="mr-2 font-mono text-[10px] uppercase text-slate-400">
                          {turn.idx} {turn.role}
                        </span>
                        {turn.text}
                      </div>
                      {violations.map((v, i) => (
                        <div
                          key={i}
                          className="ml-4 mt-1 border-l-2 border-alarm/50 pl-3 text-xs"
                        >
                          <span className="font-mono font-medium text-alarm">
                            {v.rule}
                          </span>
                          <p className="mt-0.5 italic text-slate-500">“{v.quote}”</p>
                          <p className="text-slate-600">{v.explanation}</p>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="font-mono text-sm font-medium text-slate-800">{value}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-right text-sm text-slate-800">{value}</dd>
    </div>
  );
}
