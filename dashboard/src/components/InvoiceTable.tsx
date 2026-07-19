import Link from "next/link";
import { FileText, ArrowRight } from "lucide-react";
import type { Invoice } from "@/lib/api";
import StatusBadge from "./StatusBadge";
import { formatAmount, formatDate } from "@/lib/format";

export default function InvoiceTable({ invoices }: { invoices: Invoice[] }) {
  if (invoices.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-center">
        <FileText className="text-gray-300" size={32} />
        <p className="text-sm font-medium text-gray-700">No invoices found</p>
        <p className="text-sm text-gray-400">Create your first invoice to get started.</p>
      </div>
    );
  }

  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="text-xs font-medium uppercase tracking-wide text-gray-400">
          <th className="border-b border-gray-100 py-3 pr-4">Invoice</th>
          <th className="border-b border-gray-100 py-3 pr-4">Client</th>
          <th className="border-b border-gray-100 py-3 pr-4">Amount</th>
          <th className="border-b border-gray-100 py-3 pr-4">Status</th>
          <th className="border-b border-gray-100 py-3 pr-4">Due date</th>
          <th className="border-b border-gray-100 py-3 pr-4"></th>
        </tr>
      </thead>
      <tbody>
        {invoices.map((invoice) => (
          <tr key={invoice.invoice_id} className="group border-b border-gray-50 last:border-0 hover:bg-gray-50/80">
            <td className="py-4 pr-4">
              <Link
                href={`/invoices/${invoice.invoice_id}`}
                className="font-medium text-gray-900 hover:text-brand-700"
              >
                #{invoice.invoice_number}
              </Link>
            </td>
            <td className="py-4 pr-4 text-gray-700">{invoice.client_name}</td>
            <td className="py-4 pr-4 font-medium text-gray-900">
              {formatAmount(invoice.amount, invoice.currency)}
            </td>
            <td className="py-4 pr-4">
              <StatusBadge status={invoice.status} />
            </td>
            <td className="py-4 pr-4 text-gray-500">{formatDate(invoice.due_date)}</td>
            <td className="py-4 pr-2 text-right">
              <Link
                href={`/invoices/${invoice.invoice_id}`}
                className="inline-flex items-center text-gray-300 opacity-0 transition-opacity group-hover:opacity-100 group-hover:text-brand-600"
              >
                <ArrowRight size={16} />
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
