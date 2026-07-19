"use client";

import { useEffect, useState } from "react";
import { FileStack, Clock, CheckCircle2, AlertTriangle } from "lucide-react";
import { listInvoices, type Invoice, type InvoiceStatus } from "@/lib/api";
import { formatAmount } from "@/lib/format";

const STATUSES: InvoiceStatus[] = ["draft", "sent", "paid", "cancelled"];

const STATUS_COLORS: Record<InvoiceStatus, string> = {
  draft: "bg-gray-300",
  sent: "bg-blue-400",
  paid: "bg-gradient-to-t from-brand-600 to-brand-400",
  cancelled: "bg-red-400",
};

async function fetchAllInvoices(): Promise<Invoice[]> {
  const all: Invoice[] = [];
  let cursor: string | undefined;
  do {
    const result = await listInvoices({ limit: 100, last_evaluated_key: cursor });
    all.push(...result.invoices);
    cursor = result.last_evaluated_key || undefined;
  } while (cursor);
  return all;
}

export default function AnalyticsPage() {
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAllInvoices()
      .then(setInvoices)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load analytics"));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!invoices) {
    return (
      <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl border border-gray-200 bg-white" />
        ))}
      </div>
    );
  }

  const today = new Date().toISOString().slice(0, 10);
  const thisMonth = new Date().toISOString().slice(0, 7);

  const totalInvoices = invoices.length;
  const totalOutstanding = invoices
    .filter((i) => i.status === "sent")
    .reduce((sum, i) => sum + i.amount, 0);
  const totalPaidThisMonth = invoices
    .filter((i) => i.status === "paid" && i.updated_at.slice(0, 7) === thisMonth)
    .reduce((sum, i) => sum + i.amount, 0);
  const overdueCount = invoices.filter((i) => i.status === "sent" && i.due_date < today).length;

  const countByStatus = STATUSES.reduce<Record<InvoiceStatus, number>>((acc, status) => {
    acc[status] = invoices.filter((i) => i.status === status).length;
    return acc;
  }, {} as Record<InvoiceStatus, number>);
  const maxCount = Math.max(1, ...Object.values(countByStatus));

  const currency = invoices[0]?.currency ?? "GHS";

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900">Analytics</h1>
        <p className="mt-1 text-sm text-gray-500">Overview of your receivables</p>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-5 sm:grid-cols-4">
        <StatCard
          label="Total Invoices"
          value={totalInvoices.toString()}
          icon={FileStack}
          accent="from-gray-500 to-gray-700"
          border="border-l-gray-400"
        />
        <StatCard
          label="Outstanding"
          value={formatAmount(totalOutstanding, currency)}
          icon={Clock}
          accent="from-blue-500 to-blue-700"
          border="border-l-blue-400"
        />
        <StatCard
          label="Paid This Month"
          value={formatAmount(totalPaidThisMonth, currency)}
          icon={CheckCircle2}
          accent="from-brand-500 to-brand-700"
          border="border-l-brand-500"
        />
        <StatCard
          label="Overdue"
          value={overdueCount.toString()}
          icon={AlertTriangle}
          accent="from-red-500 to-red-700"
          border="border-l-red-400"
        />
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-7 shadow-sm shadow-gray-200/50">
        <h2 className="mb-7 text-sm font-medium text-gray-500">Invoices by Status</h2>
        <div className="flex h-48 items-end gap-10 px-2">
          {STATUSES.map((status) => (
            <div key={status} className="flex flex-1 flex-col items-center gap-2.5">
              <span className="text-base font-semibold text-gray-900">{countByStatus[status]}</span>
              <div className="flex h-32 w-full items-end">
                <div
                  className={`w-full rounded-t-lg transition-all ${STATUS_COLORS[status]}`}
                  style={{ height: `${Math.max(4, (countByStatus[status] / maxCount) * 100)}%` }}
                />
              </div>
              <span className="text-xs font-medium capitalize text-gray-500">{status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  accent,
  border,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ size?: number }>;
  accent: string;
  border: string;
}) {
  return (
    <div className={`rounded-2xl border border-l-4 border-gray-200 bg-white p-5 shadow-sm shadow-gray-200/50 ${border}`}>
      <div className={`mb-3.5 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br text-white shadow-sm ${accent}`}>
        <Icon size={16} />
      </div>
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight text-gray-900">{value}</p>
    </div>
  );
}
