import type { JobRecord } from "@/lib/types";
import { usePreferences } from "@/components/PreferencesProvider";

const styles: Record<JobRecord["status"], string> = {
  queued: "bg-subtle text-muted",
  running: "bg-accent/20 text-ink",
  completed: "bg-court/15 text-court",
  failed: "bg-danger/15 text-danger"
};

export function StatusBadge({ status }: { status: JobRecord["status"] }) {
  const { t } = usePreferences();
  const label = {
    queued: t("statusQueued"),
    running: t("statusRunning"),
    completed: t("statusCompleted"),
    failed: t("statusFailed")
  }[status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${styles[status]}`}>{label}</span>;
}
