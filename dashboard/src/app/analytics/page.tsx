"use client";

import { useEffect, useState } from "react";
import { FileStack, Clock, CheckCircle2, AlertTriangle } from "lucide-react";
import { listInvoices, type Invoice, type InvoiceStatus } from "@/lib/api";
import { formatAmount } from "@/lib/format";

const STATUSES: InvoiceStatus[] = ["draft", "sent", "paid", "cancelled"];

const STATUS_COLORS: Record<InvoiceStatus, string> = {
  draft: "bg-gray-300",
  sent: "bg-blue-400",
  paid: "bg-brand-500",
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
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl border border-gray-200 bg-white" />
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
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Analytics</h1>
        <p className="mt-0.5 text-sm text-gray-500">Overview of your receivables</p>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Total Invoices"
          value={totalInvoices.toString()}
          icon={FileStack}
          accent="bg-gray-100 text-gray-600"
        />
        <StatCard
          label="Outstanding"
          value={formatAmount(totalOutstanding, currency)}
          icon={Clock}
          accent="bg-blue-50 text-blue-600"
        />
        <StatCard
          label="Paid This Month"
          value={formatAmount(totalPaidThisMonth, currency)}
          icon={CheckCircle2}
          accent="bg-brand-50 text-brand-600"
        />
        <StatCard
          label="Overdue"
          value={overdueCount.toString()}
          icon={AlertTriangle}
          accent="bg-red-50 text-red-600"
        />
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-6 text-sm font-medium text-gray-500">Invoices by Status</h2>
        <div className="flex h-44 items-end gap-8 px-2">
          {STATUSES.map((status) => (
            <div key={status} className="flex flex-1 flex-col items-center gap-2">
              <span className="text-sm font-semibold text-gray-900">{countByStatus[status]}</span>
              <div className="flex h-32 w-full items-end">
                <div
                  className={`w-full rounded-t-md transition-all ${STATUS_COLORS[status]}`}
                  style={{ height: `${Math.max(4, (countByStatus[status] / maxCount) * 100)}%` }}
                />
              </div>
              <span className="text-xs capitalize text-gray-500">{status}</span>
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
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ size?: number }>;
  accent: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className={`mb-3 flex h-8 w-8 items-center justify-center rounded-lg ${accent}`}>
        <Icon size={16} />
      </div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-gray-900">{value}</p>
    </div>
  );
}
