// The manager's audit of one call.
//
// The job of this panel is to answer "what happened, and can I trust the
// grade?", so it puts the evidence next to the verdict: every turn with the
// silence before it, every tool the agent asked for and what the guardrail
// decided, both analysis tracks with the judge's quotes against the lines that
// earned them, and what the call wrote into the agent's memory — which is what
// will steer the next call to this person.

import { useCallTrace } from "../api/hooks";
import type { CallTrace, ToolTrace, TurnSignal } from "../api/types";
import { duration, titleCase } from "./format";
import { SafetyPill, TemperaturePill } from "./Pills";

type Violation = NonNullable<CallTrace["analysis"]["safety"]>["violations"][number];

export default function CallDrawer({
  callId,
  onClose,
}: {
  callId: string | null;
  onClose: () => void;
}) {
  const { data: call, isLoading } = useCallTrace(callId);
  if (!callId) return null;

  const conversion = call?.analysis.conversion;
  const safety = call?.analysis.safety;

  // Turn index -> the violations raised against it, so the quote and the
  // explanation sit beside the line they are about.
  const flagged = new Map<number, Violation[]>();
  for (const v of safety?.violations ?? []) {
    flagged.set(v.turn, [...(flagged.get(v.turn) ?? []), v]);
  }

  return (
    <div className="fixed inset-0 z-30 flex justify-end">
      <button aria-label="Close" className="flex-1 bg-slate-900/20" onClick={onClose} />
      <aside className="flex w-full max-w-2xl flex-col overflow-y-auto border-l border-slate-200 bg-white shadow-xl">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
          <div>
            <div className="font-mono text-sm text-slate-700">{callId}</div>
            {call && (
              <div className="text-xs text-slate-500">
                {call.lead_name} · {call.lead_type} · {call.provider.transport}
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
              {conversion && (
                <section className="rounded-md border border-slate-200 p-3">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-judge">
                    Conversion
                  </h3>
                  <dl className="space-y-1">
                    <Row
                      label="Completeness"
                      value={`${Math.round(conversion.completeness * 100)}%`}
                    />
                    <Row
                      label="Next step"
                      value={conversion.next_step_secured ? conversion.next_step || "secured" : "none"}
                    />
                    <Row
                      label="Captured"
                      value={conversion.fields_captured.join(", ") || "—"}
                    />
                    <Row
                      label="Missing"
                      value={conversion.fields_missing.join(", ") || "—"}
                    />
                  </dl>
                  <div className="mt-2">
                    <TemperaturePill value={conversion.lead_temperature} />
                  </div>
                </section>
              )}

              {safety && (
                <section className="rounded-md border border-slate-200 p-3">
                  <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-judge">
                    Safety <SafetyPill verdict={safety.verdict} />
                  </h3>
                  <dl className="space-y-1">
                    <Row label="Violations" value={String(safety.violations.length)} />
                    <Row
                      label="Unverified claims"
                      value={String(safety.unverified_claims?.length ?? 0)}
                    />
                    <Row
                      label="Pressure flags"
                      value={safety.pressure_flags?.join(", ") || "—"}
                    />
                  </dl>
                </section>
              )}
            </div>

            <ToolTraceSection tools={call.tools} />
            <MemorySection call={call} />
            <ProviderSection call={call} />

            <section>
              <h3 className="mb-2 flex items-baseline justify-between text-xs font-semibold uppercase tracking-wide text-slate-500">
                <span>Transcript</span>
                <span className="font-normal normal-case tracking-normal text-slate-400">
                  gaps over 3s are dead air
                </span>
              </h3>
              <div className="space-y-2">
                {call.turns.map((turn) => (
                  <Turn
                    key={turn.idx}
                    turn={turn}
                    violations={flagged.get(turn.idx) ?? []}
                  />
                ))}
              </div>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}

// ------------------------------------------------------------------- sections

function ToolTraceSection({ tools }: { tools: ToolTrace[] }) {
  if (!tools.length) return null;
  const denied = tools.filter((t) => !t.allowed).length;

  return (
    <section className="rounded-md border border-slate-200 p-3">
      <h3 className="mb-2 flex items-baseline justify-between text-xs font-semibold uppercase tracking-wide text-slate-500">
        <span>Tool trace</span>
        <span className="font-normal normal-case tracking-normal text-slate-400">
          {denied > 0 ? `${denied} refused by the guardrail` : "all allowed"}
        </span>
      </h3>
      <ol className="space-y-1.5">
        {tools.map((tool, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span
              className={`mt-0.5 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${
                tool.allowed
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-alarm/15 text-alarm"
              }`}
            >
              {tool.allowed ? "ok" : "deny"}
            </span>
            <div className="min-w-0 flex-1">
              <span className="font-mono text-xs text-slate-800">{tool.name}</span>
              <span className="ml-2 break-all font-mono text-[11px] text-slate-500">
                {formatArgs(tool.args)}
              </span>
              {!tool.allowed && tool.reason && (
                <p className="mt-0.5 text-xs text-alarm">{tool.reason}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function MemorySection({ call }: { call: CallTrace }) {
  if (!call.memory_written.length) {
    return (
      <section className="rounded-md border border-slate-200 p-3">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Memory written
        </h3>
        <p className="text-sm text-slate-400">
          This call added nothing to the lead's memory.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-md border border-agent/30 bg-agent/5 p-3">
      <h3 className="mb-2 flex items-baseline justify-between text-xs font-semibold uppercase tracking-wide text-agent">
        <span>Memory written</span>
        <span className="font-normal normal-case tracking-normal text-slate-500">
          lead memory v{call.memory_version}
        </span>
      </h3>
      <ul className="space-y-1.5">
        {call.memory_written.map((m, i) => (
          <li key={i} className="text-sm text-slate-700">
            <span className="mr-2 rounded bg-white px-1.5 py-0.5 font-mono text-[10px] uppercase text-slate-500 ring-1 ring-slate-200">
              {m.kind}
            </span>
            {m.text}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500">
        This is what the next call to {call.lead_name.split(" ")[0]} will start from.
      </p>
    </section>
  );
}

function ProviderSection({ call }: { call: CallTrace }) {
  const { provider, message_id } = call;
  const hasLinks = provider.trace_url || provider.recording_url;
  if (!hasLinks && !provider.run_id && !message_id) return null;

  return (
    <section className="rounded-md border border-slate-200 p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Provenance
      </h3>
      <dl className="space-y-1">
        <Row label="Transport" value={provider.transport} />
        {provider.run_id !== null && (
          <Row label="Orchestrator run" value={String(provider.run_id)} />
        )}
        {provider.disposition && (
          <Row label="Disposition" value={provider.disposition} />
        )}
        {message_id && <Row label="Follow-up drafted" value={message_id} />}
      </dl>
      {hasLinks && (
        <div className="mt-2 flex flex-wrap gap-3 text-sm">
          {provider.recording_url && (
            <a
              className="text-agent hover:underline"
              href={provider.recording_url}
              target="_blank"
              rel="noreferrer"
            >
              Recording ↗
            </a>
          )}
          {provider.trace_url && (
            <a
              className="text-agent hover:underline"
              href={provider.trace_url}
              target="_blank"
              rel="noreferrer"
            >
              Orchestrator trace ↗
            </a>
          )}
        </div>
      )}
    </section>
  );
}

function Turn({ turn, violations }: { turn: TurnSignal; violations: Violation[] }) {
  const isFlagged = violations.length > 0 || turn.flagged;

  return (
    <div>
      {/* The silence before this turn, shown only when it is worth noticing. */}
      {turn.gap_ms !== null && (turn.dead_air || turn.is_agent_latency) && (
        <div className="mb-1 flex items-center gap-2 pl-1 text-[10px] font-mono uppercase tracking-wide">
          <span className={turn.dead_air ? "text-alarm" : "text-slate-400"}>
            {(turn.gap_ms / 1000).toFixed(1)}s
          </span>
          <span className="text-slate-400">
            {turn.dead_air ? "dead air" : "agent latency"}
          </span>
        </div>
      )}

      <div
        className={`rounded-md px-3 py-2 text-sm ${
          isFlagged
            ? "border border-alarm/40 bg-alarm/5"
            : turn.is_handoff
              ? "border border-human/40 bg-human/5"
              : turn.role === "agent"
                ? "bg-slate-50 text-slate-600"
                : "bg-white ring-1 ring-slate-200"
        }`}
      >
        <span className="mr-2 font-mono text-[10px] uppercase text-slate-400">
          {turn.idx} {turn.role}
        </span>
        {turn.text}
        {turn.is_handoff && (
          <span className="ml-2 rounded bg-human/15 px-1.5 py-0.5 font-mono text-[10px] uppercase text-human">
            handoff
          </span>
        )}
      </div>

      {violations.map((v, i) => (
        <div key={i} className="ml-4 mt-1 border-l-2 border-alarm/50 pl-3 text-xs">
          <span className="font-mono font-medium text-alarm">{v.rule}</span>
          <p className="mt-0.5 italic text-slate-500">“{v.quote}”</p>
          <p className="text-slate-600">{v.explanation}</p>
        </div>
      ))}
    </div>
  );
}

// -------------------------------------------------------------------- pieces

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (!entries.length) return "";
  return entries
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join("  ");
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
