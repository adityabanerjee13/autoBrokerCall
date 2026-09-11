import { useNavigate } from "react-router-dom";

export const ROLES = [
  { key: "broker", label: "Broker" },
  { key: "client", label: "Client" },
  { key: "manager", label: "Manager" },
] as const;

export type RoleKey = (typeof ROLES)[number]["key"];

export const STORED_ROLE_KEY = "role";

export function storedRole(): RoleKey {
  const saved = localStorage.getItem(STORED_ROLE_KEY);
  return ROLES.some((r) => r.key === saved) ? (saved as RoleKey) : "broker";
}

export function RoleToggle({ active }: { active: RoleKey }) {
  const navigate = useNavigate();

  return (
    <div
      role="tablist"
      aria-label="Dashboard"
      className="inline-flex rounded-full border border-slate-300 bg-white p-0.5"
    >
      {ROLES.map(({ key, label }) => {
        const selected = key === active;
        return (
          <button
            key={key}
            role="tab"
            aria-selected={selected}
            onClick={() => {
              localStorage.setItem(STORED_ROLE_KEY, key);
              navigate(`/${key}`);
            }}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              selected
                ? "bg-slate-800 text-white"
                : "bg-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
