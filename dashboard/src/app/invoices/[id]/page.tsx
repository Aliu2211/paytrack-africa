"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Download, Sparkles, Quote } from "lucide-react";
import {
  getInvoice,
  updateInvoice,
  generatePdf,
  generateCollectionsMessage,
  type Invoice,
  type InvoiceStatus,
} from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { formatAmount, formatDate } from "@/lib/format";

const VALID_TRANSITIONS: Record<InvoiceStatus, InvoiceStatus[]> = {
  draft: ["sent", "cancelled"],
  sent: ["paid"],
  paid: [],
  cancelled: [],
};

export default function InvoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  const [generatingMessage, setGeneratingMessage] = useState(false);
  const [collectionsMessage, setCollectionsMessage] = useState<string | null>(null);

  useEffect(() => {
    getInvoice(id)
      .then(setInvoice)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load invoice"))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleTransition(status: InvoiceStatus) {
    setUpdating(true);
    setError(null);
    try {
      const updated = await updateInvoice(id, { status });
      setInvoice(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setUpdating(false);
    }
  }

  async function handleDownloadPdf() {
    setGeneratingPdf(true);
    setError(null);
    try {
      await generatePdf(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate PDF");
    } finally {
      setGeneratingPdf(false);
    }
  }

  async function handleGenerateCollectionsMessage() {
    setGeneratingMessage(true);
    setError(null);
    try {
      const result = await generateCollectionsMessage(id);
      setCollectionsMessage(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate collections message");
    } finally {
      setGeneratingMessage(false);
    }
  }

  const backLink = (
    <Link href="/invoices" className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-brand-700">
      <ArrowLeft size={14} />
      Back to invoices
    </Link>
  );

  if (loading) {
    return (
      <div>
        {backLink}
        <div className="mt-4 h-64 animate-pulse rounded-xl border border-gray-200 bg-white" />
      </div>
    );
  }
  if (error && !invoice) {
    return (
      <div>
        {backLink}
        <p className="mt-4 text-sm text-red-600">{error}</p>
      </div>
    );
  }
  if (!invoice) return null;

  const validNextStatuses = VALID_TRANSITIONS[invoice.status];

  return (
    <div>
      {backLink}

      <div className="mt-5 rounded-2xl border border-gray-200 bg-white p-8 shadow-sm shadow-gray-200/50">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
              Invoice #{invoice.invoice_number}
            </h1>
            <p className="mt-1.5 text-sm text-gray-500">{invoice.client_name}</p>
          </div>
          <StatusBadge status={invoice.status} />
        </div>

        <dl className="grid grid-cols-2 gap-x-8 gap-y-5 rounded-xl bg-gradient-to-br from-gray-50 to-gray-50/50 p-5 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">Client email</dt>
            <dd className="mt-1.5 text-gray-900">{invoice.client_email}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">Amount</dt>
            <dd className="mt-1.5 text-base font-semibold text-gray-900">
              {formatAmount(invoice.amount, invoice.currency)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">Due date</dt>
            <dd className="mt-1.5 text-gray-900">{formatDate(invoice.due_date)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">Created</dt>
            <dd className="mt-1.5 text-gray-900">{formatDate(invoice.created_at.slice(0, 10))}</dd>
          </div>
          {invoice.description && (
            <div className="col-span-2 sm:col-span-4">
              <dt className="text-xs font-medium uppercase tracking-wide text-gray-400">Description</dt>
              <dd className="mt-1.5 text-gray-900">{invoice.description}</dd>
            </div>
          )}
        </dl>

        {error && <p className="mt-5 rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-700">{error}</p>}

        <div className="mt-7 flex flex-wrap gap-2.5 border-t border-gray-100 pt-6">
          {validNextStatuses.map((status) => (
            <button
              key={status}
              onClick={() => handleTransition(status)}
              disabled={updating}
              className="rounded-lg bg-gradient-to-b from-brand-500 to-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-md shadow-brand-600/20 transition-all hover:shadow-lg hover:shadow-brand-600/25 disabled:opacity-50"
            >
              Mark as {status}
            </button>
          ))}
          <button
            onClick={handleDownloadPdf}
            disabled={generatingPdf}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <Download size={15} />
            {generatingPdf ? "Generating..." : "Download PDF"}
          </button>
          <button
            onClick={handleGenerateCollectionsMessage}
            disabled={generatingMessage}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <Sparkles size={15} />
            {generatingMessage ? "Generating..." : "Collections Message"}
          </button>
        </div>

        {collectionsMessage && (
          <div className="mt-5 flex gap-3 rounded-xl border border-brand-100 bg-gradient-to-br from-brand-50 to-white p-5">
            <Quote className="mt-0.5 shrink-0 text-brand-500" size={18} />
            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-brand-700">
                AI Collections Message
              </p>
              <p className="text-sm leading-relaxed text-gray-800">{collectionsMessage}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
