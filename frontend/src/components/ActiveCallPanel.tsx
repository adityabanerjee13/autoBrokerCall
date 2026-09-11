import { useEffect, useRef } from "react";
import { useActiveCall } from "../api/hooks";
import { duration, rentRange, titleCase } from "./format";
import { LeadTypePill } from "./Pills";

export default function ActiveCallPanel() {
  const { data: call } = useActiveCall();
  const scroller = useRef<HTMLDivElement>(null);
  const turnCount = call?.transcript.length ?? 0;

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turnCount]);

  if (!call) return null;

  const { lead } = call;

  return (
    <section className="panel overflow-hidden">
      <div className="panel-head">
        <h2 className="panel-title">Ongoing call</h2>
        <span className="font-mono text-xs text-slate-400">
          {call.call_id} · {duration(call.elapsed_s)}
        </span>
      </div>

      {call.escalated && (
        <div className="flex items-center gap-2 border-b border-alarm/30 bg-alarm/10 px-4 py-2.5 text-sm font-medium text-alarm">
          <span className="h-2 w-2 rounded-full bg-alarm" />
          Escalated · {titleCase((call.escalation_reason ?? "").toLowerCase())} ·
          handoff message played
        </div>
      )}

      <div className="grid gap-4 p-4 lg:grid-cols-[260px_1fr]">
        <div className="space-y-3">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="text-sm font-semibold text-slate-800">
              {lead.first_name} {lead.last_name}
            </div>
            <div className="mt-1 font-mono text-[11px] text-slate-400">
              {lead.lead_id} · {lead.phone}
            </div>
            <div className="mt-2">
              <LeadTypePill type={lead.lead_type} />
            </div>
            <dl className="mt-3 space-y-1 text-xs text-slate-600">
              {lead.lead_type === "renter" ? (
                <>
                  <div>
                    <dt className="inline text-slate-400">Budget </dt>
                    <dd className="inline">
                      {rentRange(lead.monthly_rent_min, lead.monthly_rent_max)}
                    </dd>
                  </div>
                  <div>
                    <dt className="inline text-slate-400">Config </dt>
                    <dd className="inline">{lead.bhk_config ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="inline text-slate-400">Areas </dt>
                    <dd className="inline">
                      {lead.preferred_areas.join(", ") || "—"}
                    </dd>
                  </div>
                </>
              ) : (
                <div>
                  <dt className="inline text-slate-400">Property </dt>
                  <dd className="inline">{lead.subject_property_address ?? "—"}</dd>
                </div>
              )}
            </dl>
          </div>

          <div>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Tool calls
            </h3>
            {call.tool_calls.length === 0 ? (
              <p className="text-xs text-slate-400">None yet.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {call.tool_calls.map((t, i) => (
                  <span
                    key={`${t.name}-${i}`}
                    title={t.allowed ? "allowed" : `denied: ${t.reason}`}
                    className={`pill font-mono ${
                      t.allowed
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-alarm/10 text-alarm"
                    }`}
                  >
                    {t.name}
                    {!t.allowed && (
                      <span className="ml-1 opacity-70">· {t.reason}</span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div
          ref={scroller}
          className="max-h-[380px] space-y-2.5 overflow-y-auto rounded-md border border-slate-200 bg-slate-50/60 p-3"
        >
          {call.transcript.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">
              {call.status === "ringing"
                ? "Ringing — waiting for the lead to pick up."
                : "Connecting…"}
            </p>
          ) : (
            call.transcript.map((turn) => (
              <div
                key={turn.idx}
                className={`flex ${turn.role === "lead" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[78%] rounded-lg px-3 py-2 text-sm ${
                    turn.role === "agent"
                      ? "bg-white text-slate-500 ring-1 ring-slate-200"
                      : "bg-agent text-white"
                  }`}
                >
                  <div
                    className={`mb-0.5 text-[10px] uppercase tracking-wide ${
                      turn.role === "agent" ? "text-slate-400" : "text-white/70"
                    }`}
                  >
                    {turn.role}
                  </div>
                  {turn.text}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
