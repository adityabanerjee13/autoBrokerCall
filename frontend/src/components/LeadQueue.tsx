import { useState } from "react";
import { useActiveCall, useQueue, useStartCall } from "../api/hooks";
import type { LeadRow } from "../api/types";
import { rentRange, when } from "./format";
import { LeadStatusPill, LeadTypePill } from "./Pills";

function requirement(lead: LeadRow) {
  if (lead.lead_type === "lender") {
    return lead.subject_property_address ?? "—";
  }
  const areas = lead.preferred_areas.length ? lead.preferred_areas.join(", ") : "any area";
  return `${rentRange(lead.monthly_rent_min, lead.monthly_rent_max)} · ${
    lead.bhk_config ?? "any"
  } · ${areas}`;
}

export default function LeadQueue({ readOnly = false }: { readOnly?: boolean }) {
  const { data: leads, isLoading } = useQueue();
  const { data: active } = useActiveCall();
  const startCall = useStartCall();
  const [error, setError] = useState<string | null>(null);

  const callInProgress = Boolean(active);

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="panel-title">Lead queue</h2>
        <span className="text-xs text-slate-400">
          {leads?.length ?? 0} waiting
        </span>
      </div>

      {error && (
        <p className="border-b border-alarm/20 bg-alarm/5 px-4 py-2 text-sm text-alarm">
          {error}
        </p>
      )}

      {isLoading && !leads ? (
        <p className="empty">Loading…</p>
      ) : !leads?.length ? (
        <p className="empty">No leads in the queue.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-slate-100">
              <tr>
                <th className="th">Name</th>
                <th className="th">Type</th>
                <th className="th">Phone</th>
                <th className="th">Requirement</th>
                <th className="th">Status</th>
                <th className="th">Waiting since</th>
                {!readOnly && <th className="th" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {leads.map((lead) => (
                <tr key={lead.lead_id} className="hover:bg-slate-50/70">
                  <td className="td font-medium text-slate-800">
                    {lead.first_name} {lead.last_name}
                    <div className="font-mono text-[11px] text-slate-400">
                      {lead.lead_id}
                    </div>
                  </td>
                  <td className="td">
                    <LeadTypePill type={lead.lead_type} />
                  </td>
                  <td className="td font-mono text-xs text-slate-500">{lead.phone}</td>
                  <td className="td text-slate-600">{requirement(lead)}</td>
                  <td className="td">
                    <LeadStatusPill status={lead.lead_status} />
                  </td>
                  <td className="td text-slate-500">{when(lead.created_at)}</td>
                  {!readOnly && (
                    <td className="td text-right">
                      <button
                        className="btn-primary"
                        disabled={callInProgress || startCall.isPending}
                        title={
                          callInProgress
                            ? "A call is already in progress"
                            : undefined
                        }
                        onClick={() => {
                          setError(null);
                          startCall.mutate(lead.lead_id, {
                            onError: (e: Error) => setError(e.message),
                          });
                        }}
                      >
                        Call now
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
