import { useState } from "react";
import { useCreateLead } from "../api/hooks";
import type { Furnishing, LeadType, NewLead } from "../api/types";

// The qualifying fields are optional on purpose. Capturing a renter's budget,
// areas and configuration is the agent's job on the call; typing a guess in
// here would be stored as though the caller had said it, and the analyzer would
// then grade the call as having captured something it never asked about.

const EMPTY: NewLead = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  lead_type: "renter",
  monthly_rent_min: null,
  monthly_rent_max: null,
  bhk_config: null,
  furnishing: null,
  preferred_areas: [],
  subject_property_address: null,
};

export default function AddLeadForm({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState<NewLead>(EMPTY);
  const [areas, setAreas] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const createLead = useCreateLead();

  const renter = form.lead_type === "renter";
  const set = <K extends keyof NewLead>(key: K, value: NewLead[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    createLead.mutate(
      {
        ...form,
        preferred_areas: renter
          ? areas.split(",").map((a) => a.trim()).filter(Boolean)
          : [],
      },
      {
        onSuccess: (res) => {
          setCreated(res.lead_id);
          setForm(EMPTY);
          setAreas("");
        },
        onError: (e: Error) => setError(e.message),
      }
    );
  }

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-slate-900/30 p-6">
      <form
        onSubmit={submit}
        className="panel w-full max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-head">
          <h2 className="panel-title">Add a lead</h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>

        {created && (
          <p className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800">
            Created <span className="font-mono">{created}</span> — it is in the
            broker queue, ready to call. Add another or close.
          </p>
        )}
        {error && (
          <p className="border-b border-alarm/20 bg-alarm/5 px-4 py-2 text-sm text-alarm">
            {error}
          </p>
        )}

        <div className="space-y-4 p-4">
          <fieldset>
            <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Lead type
            </legend>
            <div className="inline-flex rounded-md border border-slate-300 p-0.5">
              {(["renter", "lender"] as LeadType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => set("lead_type", t)}
                  className={`rounded px-4 py-1.5 text-sm font-medium capitalize transition-colors ${
                    form.lead_type === t
                      ? "bg-slate-800 text-white"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {t === "lender" ? "Owner" : "Renter"}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="First name" required>
              <input
                className="input"
                required
                maxLength={60}
                value={form.first_name}
                onChange={(e) => set("first_name", e.target.value)}
              />
            </Field>
            <Field label="Last name">
              <input
                className="input"
                maxLength={60}
                value={form.last_name}
                onChange={(e) => set("last_name", e.target.value)}
              />
            </Field>
            <Field label="Phone" required hint="International format, e.g. +919812345678">
              <input
                className="input font-mono"
                required
                placeholder="+919812345678"
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
              />
            </Field>
            <Field label="Email">
              <input
                className="input"
                type="email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
              />
            </Field>
          </div>

          {renter ? (
            <>
              <p className="text-xs text-slate-500">
                Everything below is optional — the agent captures it on the call.
                Fill it in only if the caller has already told you.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Budget min (₹/mo)">
                  <input
                    className="input"
                    type="number"
                    min={0}
                    value={form.monthly_rent_min ?? ""}
                    onChange={(e) =>
                      set("monthly_rent_min", e.target.value ? Number(e.target.value) : null)
                    }
                  />
                </Field>
                <Field label="Budget max (₹/mo)">
                  <input
                    className="input"
                    type="number"
                    min={0}
                    value={form.monthly_rent_max ?? ""}
                    onChange={(e) =>
                      set("monthly_rent_max", e.target.value ? Number(e.target.value) : null)
                    }
                  />
                </Field>
                <Field label="Configuration">
                  <input
                    className="input"
                    placeholder="3BHK"
                    value={form.bhk_config ?? ""}
                    onChange={(e) => set("bhk_config", e.target.value || null)}
                  />
                </Field>
                <Field label="Furnishing">
                  <select
                    className="input"
                    value={form.furnishing ?? ""}
                    onChange={(e) =>
                      set("furnishing", (e.target.value || null) as Furnishing | null)
                    }
                  >
                    <option value="">Not stated</option>
                    <option value="unfurnished">Unfurnished</option>
                    <option value="semi">Semi furnished</option>
                    <option value="full">Fully furnished</option>
                  </select>
                </Field>
              </div>
              <Field label="Preferred areas" hint="Comma separated, e.g. Sector 82, Sector 84">
                <input
                  className="input"
                  placeholder="Sector 82, Sector 84"
                  value={areas}
                  onChange={(e) => setAreas(e.target.value)}
                />
              </Field>
            </>
          ) : (
            <Field
              label="Property address"
              required
              hint="The property they have listed with us. The agent cannot proceed without it."
            >
              <input
                className="input"
                required
                placeholder="B-1204, Emerald Court, Sector 93, Gurugram"
                value={form.subject_property_address ?? ""}
                onChange={(e) => set("subject_property_address", e.target.value || null)}
              />
            </Field>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-4 py-3">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={createLead.isPending}>
            {createLead.isPending ? "Adding…" : "Add to queue"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">
        {label}
        {required && <span className="ml-0.5 text-alarm">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}
