import { AppShell } from "@/components/AppShell";
import { MetricsDashboard } from "@/components/MetricsDashboard";

export default function MetricsPage() {
  return (
    <AppShell wide>
      <MetricsDashboard />
    </AppShell>
  );
}
