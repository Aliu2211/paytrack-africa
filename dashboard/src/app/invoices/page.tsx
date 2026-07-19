"use client";

import { useEffect, useState, useCallback } from "react";
import { Plus, Search, ChevronLeft, ChevronRight } from "lucide-react";
import { listInvoices, type Invoice, type InvoiceStatus } from "@/lib/api";
import InvoiceTable from "@/components/InvoiceTable";
import CreateInvoiceModal from "@/components/CreateInvoiceModal";

const STATUS_OPTIONS: (InvoiceStatus | "")[] = ["", "draft", "sent", "paid", "cancelled"];

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | "">("");
  const [search, setSearch] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorStack, setCursorStack] = useState<string[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  const loadInvoices = useCallback(
    async (afterKey: string | null) => {
      setLoading(true);
      setError(null);
      try {
        const result = await listInvoices({
          status: statusFilter || undefined,
          last_evaluated_key: afterKey || undefined,
        });
        setInvoices(result.invoices);
        setNextCursor(result.last_evaluated_key);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load invoices");
      } finally {
        setLoading(false);
      }
    },
    [statusFilter]
  );

  useEffect(() => {
    setCursor(null);
    setCursorStack([]);
    loadInvoices(null);
  }, [loadInvoices]);

  function goNext() {
    if (!nextCursor) return;
    setCursorStack((stack) => [...stack, cursor ?? ""]);
    setCursor(nextCursor);
    loadInvoices(nextCursor);
  }

  function goPrevious() {
    const stack = [...cursorStack];
    const previous = stack.pop() ?? null;
    setCursorStack(stack);
    setCursor(previous || null);
    loadInvoices(previous || null);
  }

  const filteredInvoices = search
    ? invoices.filter((invoice) => invoice.client_name.toLowerCase().includes(search.toLowerCase()))
    : invoices;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Invoices</h1>
          <p className="mt-0.5 text-sm text-gray-500">Manage and track client invoices</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-1.5 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
        >
          <Plus size={16} />
          Create Invoice
        </button>
      </div>

      <div className="mb-4 flex gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
          <input
            placeholder="Search by client name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm shadow-sm outline-none transition-shadow focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as InvoiceStatus | "")}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none transition-shadow focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        >
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {status ? status[0].toUpperCase() + status.slice(1) : "All statuses"}
            </option>
          ))}
        </select>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        {loading && <TableSkeleton />}
        {error && !loading && (
          <p className="py-8 text-center text-sm text-red-600">{error}</p>
        )}
        {!loading && !error && <InvoiceTable invoices={filteredInvoices} />}
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          onClick={goPrevious}
          disabled={cursorStack.length === 0}
          className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft size={14} />
          Previous
        </button>
        <button
          onClick={goNext}
          disabled={!nextCursor}
          className="flex items-center gap-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
          <ChevronRight size={14} />
        </button>
      </div>

      {showCreateModal && (
        <CreateInvoiceModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => loadInvoices(cursor)}
        />
      )}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-3 py-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-10 rounded-md bg-gray-100" />
      ))}
    </div>
  );
}
