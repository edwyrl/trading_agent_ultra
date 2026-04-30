import { AlertTriangle, CheckCircle2, Clock3, Loader2, XCircle } from "lucide-react";
import type { SignalRunStatus } from "../types/api";

const LABELS: Record<SignalRunStatus, string> = {
  PENDING: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed",
  CANCELED: "Canceled",
};

export function StatusBadge({ status }: { status: SignalRunStatus }) {
  const Icon =
    status === "SUCCEEDED"
      ? CheckCircle2
      : status === "FAILED"
        ? AlertTriangle
        : status === "RUNNING"
          ? Loader2
          : status === "CANCELED"
            ? XCircle
            : Clock3;
  return (
    <span className={`status-badge status-${status.toLowerCase()}`}>
      <Icon size={15} aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}
