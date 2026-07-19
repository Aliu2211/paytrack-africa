import type { InvoiceStatus } from "@/lib/api";

const STYLES: Record<InvoiceStatus, { badge: string; dot: string }> = {
  draft: { badge: "bg-gray-100 text-gray-700", dot: "bg-gray-400" },
  sent: { badge: "bg-blue-50 text-blue-700", dot: "bg-blue-500" },
  paid: { badge: "bg-brand-50 text-brand-700", dot: "bg-brand-500" },
  cancelled: { badge: "bg-red-50 text-red-700", dot: "bg-red-500" },
};

export default function StatusBadge({ status }: { status: InvoiceStatus }) {
  const style = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${style.badge}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {status}
    </span>
  );
}
