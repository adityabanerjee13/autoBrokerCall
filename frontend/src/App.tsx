import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { RoleToggle, storedRole, type RoleKey } from "./components/RoleToggle";
import { useActiveCall } from "./api/hooks";
import BrokerDashboard from "./dashboards/BrokerDashboard";
import ClientDashboard from "./dashboards/ClientDashboard";
import ManagerDashboard from "./dashboards/ManagerDashboard";

function LiveIndicator() {
  const { data } = useActiveCall();
  const live = Boolean(data);
  const ringing = data?.status === "ringing";
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <span className="relative flex h-2.5 w-2.5">
        {live && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
            live ? (ringing ? "bg-amber-500" : "bg-emerald-500") : "bg-slate-300"
          }`}
        />
      </span>
      {live ? (ringing ? "Ringing" : "Call in progress") : "No active call"}
    </div>
  );
}

export default function App() {
  const { pathname } = useLocation();
  const active = (pathname.split("/")[1] || "broker") as RoleKey;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto grid max-w-[1400px] grid-cols-3 items-center px-6 py-3">
          <div className="flex items-baseline gap-2">
            <span className="text-base font-semibold tracking-tight text-slate-900">
              brokerAgent
            </span>
            <span className="hidden text-xs text-slate-400 xl:inline">
              Gurugram rentals
            </span>
          </div>
          <div className="flex justify-center">
            <RoleToggle active={active} />
          </div>
          <div className="flex justify-end">
            <LiveIndicator />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-6 py-6">
        <Routes>
          <Route path="/" element={<Navigate to={`/${storedRole()}`} replace />} />
          <Route path="/broker" element={<BrokerDashboard />} />
          <Route path="/client" element={<ClientDashboard />} />
          <Route path="/manager" element={<ManagerDashboard />} />
          <Route path="*" element={<Navigate to="/broker" replace />} />
        </Routes>
      </main>
    </div>
  );
}
