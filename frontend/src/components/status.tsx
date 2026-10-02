import { cn } from "@/lib/utils";

const severityClass: Record<string, string> = {
  "SEV-1": "bg-[#3a1717] text-[#ffb4b4] border-[#6b2a2a]",
  "SEV-2": "bg-[#3a2a12] text-[#f5c16c] border-[#6b4e1d]",
  "SEV-3": "bg-[#2c2a16] text-[#e7d48a] border-[#5a5224]",
  "SEV-4": "bg-elevated text-muted border-line",
};

const statusClass: Record<string, string> = {
  investigating: "text-[#9eb8f5]",
  awaiting_approval: "text-[#f5c16c]",
  executing: "text-[#9eb8f5]",
  resolved: "text-[#7ddeb4]",
  closed: "text-muted",
};

export function SeverityBadge({ severity }: { severity: string | null }) {
  const label = severity ?? "UNTRIAGED";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-xs",
        severityClass[label] ?? severityClass["SEV-4"],
      )}
    >
      {label}
    </span>
  );
}

export function StatusText({ status }: { status: string }) {
  return (
    <span className={cn("text-sm capitalize", statusClass[status] ?? "text-muted")}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: string }) {
  const styles: Record<string, string> = {
    LOW: "border-[#245c45] text-[#7ddeb4]",
    MEDIUM: "border-[#6b4e1d] text-[#f5c16c]",
    HIGH: "border-[#6b2a2a] text-[#ffb4b4]",
  };
  return (
    <span className={cn("rounded-md border px-2 py-0.5 font-mono text-xs", styles[risk] ?? styles.LOW)}>
      {risk}
    </span>
  );
}
