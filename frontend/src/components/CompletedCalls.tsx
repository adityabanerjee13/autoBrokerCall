import { Fragment, useState } from "react";
import { useCompleted, useSendMessage } from "../api/hooks";
import type { CompletedCall } from "../api/types";
import { duration, titleCase, when } from "./format";
import { AnalysisStatusPill, EscalationBadge } from "./Pills";

type ButtonState = {
  label: string;
  disabled: boolean;
  className: string;
};

function buttonState(call: CompletedCall, pending: boolean): ButtonState {
  if (!call.message)
    return { label: "Draft pending", disabled: true, className: "btn-ghost" };
  if (pending || call.message.status === "sending")
    return { label: "Sending…", disabled: true, className: "btn-primary" };
  switch (call.message.status) {
    case "sent":
      return { label: "Sent ✓", disabled: true, className: "btn-ghost" };
    case "partial":
    case "failed":
      return { label: "Retry", disabled: false, className: "btn-danger" };
    default:
      return { label: "Send follow-up", disabled: false, className: "btn-primary" };
  }
}

function outcome(call: CompletedCall): string {
  if (call.escalated) return "Handed to a colleague";
  return call.analysis_status === "done" ? "Completed" : "Completed, grading";
}

export default function CompletedCalls({ readOnly = false }: { readOnly?: boolean }) {
  const { data: calls, isLoading } = useCompleted();
  const send = useSendMessage();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Completed calls</h2>
        <span className="text-xs text-slate-400">{calls?.length ?? 0} calls</span>
      </div>

      {error && (
        <p className="border-b border-alarm/20 bg-alarm/5 px-4 py-2 text-sm text-alarm">
          {error}
        </p>
      )}

      {isLoading && !calls ? (
        <p className="empty">Loading…</p>
      ) : !calls?.length ? (
        <p className="empty">No completed calls yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-slate-100">
              <tr>
                <th className="th">Lead</th>
                <th className="th">Ended</th>
                <th className="th">Duration</th>
                <th className="th">Outcome</th>
                <th className="th">Analysis</th>
                {!readOnly && <th className="th" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {calls.map((call) => {
                const state = buttonState(
                  call,
                  send.isPending && send.variables === call.message?.message_id
                );
                const isOpen = expanded === call.call_id;
                return (
                  <Fragment key={call.call_id}>
                    <tr className="hover:bg-slate-50/70">
                      <td className="td font-medium text-slate-800">
                        {call.lead.first_name} {call.lead.last_name}
                        <div className="font-mono text-[11px] text-slate-400">
                          {call.call_id}
                        </div>
                      </td>
                      <td className="td text-slate-500">{when(call.ended_at)}</td>
                      <td className="td font-mono text-slate-600">
                        {duration(call.duration_s)}
                      </td>
                      <td className="td">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span
                            className={
                              call.escalated ? "text-alarm" : "text-slate-600"
                            }
                          >
                            {outcome(call)}
                          </span>
                          <EscalationBadge reason={call.escalation_reason} />
                        </div>
                      </td>
                      <td className="td">
                        <AnalysisStatusPill status={call.analysis_status} />
                      </td>
                      {!readOnly && (
                        <td className="td">
                          <div className="flex items-center justify-end gap-2">
                            {call.message && (
                              <button
                                className="text-xs text-slate-500 underline-offset-2 hover:underline"
                                onClick={() =>
                                  setExpanded(isOpen ? null : call.call_id)
                                }
                              >
                                {isOpen ? "Hide draft" : "Preview draft"}
                              </button>
                            )}
                            <button
                              className={state.className}
                              disabled={state.disabled}
                              onClick={() => {
                                setError(null);
                                send.mutate(call.message!.message_id, {
                                  onError: (e: Error) => setError(e.message),
                                });
                              }}
                            >
                              {state.label}
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                    {isOpen && call.message && (
                      <tr className="bg-slate-50">
                        <td className="td" colSpan={readOnly ? 5 : 6}>
                          <div className="grid gap-3 md:grid-cols-2">
                            <div className="rounded-md border border-slate-200 bg-white p-3">
                              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                                WhatsApp
                              </div>
                              <p className="whitespace-pre-wrap text-sm text-slate-700">
                                {call.message.whatsapp_preview}
                              </p>
                            </div>
                            <div className="rounded-md border border-slate-200 bg-white p-3">
                              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                                Email subject
                              </div>
                              <p className="text-sm text-slate-700">
                                {call.message.email_subject}
                              </p>
                              <p className="mt-2 text-xs text-slate-400">
                                One click sends both channels · status{" "}
                                {titleCase(call.message.status)}
                              </p>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
