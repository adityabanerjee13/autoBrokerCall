import ActiveCallPanel from "../components/ActiveCallPanel";
import CompletedCalls from "../components/CompletedCalls";
import LeadQueue from "../components/LeadQueue";

export default function BrokerDashboard() {
  return (
    <div className="space-y-6">
      <LeadQueue />
      <ActiveCallPanel />
      <CompletedCalls />
    </div>
  );
}
