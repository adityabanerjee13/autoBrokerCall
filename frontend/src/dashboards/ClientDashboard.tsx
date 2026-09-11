import { useEffect, useState } from "react";
import { useClientDashboard, useLenders } from "../api/hooks";
import { absolute, rentPerMonth } from "../components/format";
import { PropertyStatusPill } from "../components/Pills";

// This page shows an owner their own listings. It deliberately renders no
// tenant identity, no tenant budget and no reason anyone passed - the API does
// not send those, and nothing here should start asking for them.

const STORED_OWNER_KEY = "client_owner";

export default function ClientDashboard() {
  const { data: lenders } = useLenders();
  const [ownerId, setOwnerId] = useState<string | null>(() =>
    localStorage.getItem(STORED_OWNER_KEY)
  );

  useEffect(() => {
    if (!ownerId && lenders?.length) setOwnerId(lenders[0].lead_id);
  }, [lenders, ownerId]);

  useEffect(() => {
    if (ownerId) localStorage.setItem(STORED_OWNER_KEY, ownerId);
  }, [ownerId]);

  const { data, isLoading } = useClientDashboard(ownerId);
  const interestFor = (pid: string) =>
    data?.interest.find((i) => i.property_id === pid);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">My properties</h1>
          <p className="text-sm text-slate-500">
            Interest and viewings on the homes you have listed with us.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          Viewing as
          <select
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
            value={ownerId ?? ""}
            onChange={(e) => setOwnerId(e.target.value)}
          >
            {(lenders ?? []).map((l) => (
              <option key={l.lead_id} value={l.lead_id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Listings &amp; interest</h2>
          <span className="text-xs text-slate-400">
            {data?.properties.length ?? 0} properties
          </span>
        </div>
        {isLoading && !data ? (
          <p className="empty">Loading…</p>
        ) : !data?.properties.length ? (
          <p className="empty">No properties listed yet.</p>
        ) : (
          <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.properties.map((p) => {
              const interest = interestFor(p.property_id);
              const shown = interest?.shown_count ?? 0;
              const liked = interest?.liked_count ?? 0;
              const scale = Math.max(shown, liked, 1);
              return (
                <article
                  key={p.property_id}
                  className="rounded-lg border border-slate-200 p-4 transition-shadow hover:shadow-sm"
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold leading-snug text-slate-800">
                      {p.address}
                    </h3>
                    <PropertyStatusPill status={p.status} />
                  </div>
                  <div className="mt-1 font-mono text-[11px] text-slate-400">
                    {p.property_id}
                  </div>
                  <div className="mt-3 flex items-baseline gap-2">
                    <span className="text-lg font-semibold text-slate-900">
                      {rentPerMonth(p.monthly_rent)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {p.bhk_config} · {p.furnishing}
                    </span>
                  </div>

                  <div className="mt-4 space-y-1.5 border-t border-slate-100 pt-3">
                    <Bar label="Shown" value={shown} scale={scale} tone="bg-agent" />
                    <Bar label="Liked" value={liked} scale={scale} tone="bg-human" />
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">Upcoming viewings</h2>
        </div>
        {!data?.upcoming.length ? (
          <p className="empty">No viewings booked.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.upcoming.map((u, i) => (
              <li
                key={`${u.property_id}-${i}`}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
              >
                <div className="text-sm text-slate-800">
                  <span className="font-medium">{u.first_name}</span>
                  <span className="text-slate-400"> · </span>
                  <span className="font-mono text-xs text-slate-500">
                    {u.property_id}
                  </span>
                </div>
                <div className="text-sm text-slate-600">
                  {absolute(u.appointment_datetime)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Bar({
  label,
  value,
  scale,
  tone,
}: {
  label: string;
  value: number;
  scale: number;
  tone: string;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-12 shrink-0 text-slate-500">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${tone}`}
          style={{ width: `${(value / scale) * 100}%` }}
        />
      </div>
      <span className="w-4 shrink-0 text-right font-medium tabular-nums text-slate-700">
        {value}
      </span>
    </div>
  );
}
