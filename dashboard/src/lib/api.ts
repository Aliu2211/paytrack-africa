import { fetchAuthSession } from "aws-amplify/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

export type InvoiceStatus = "draft" | "sent" | "paid" | "cancelled";

export interface LineItem {
  description: string;
  amount: number;
}

export interface Invoice {
  tenant_id: string;
  invoice_id: string;
  invoice_number: number;
  client_name: string;
  client_email: string;
  amount: number;
  currency: string;
  due_date: string;
  description: string;
  line_items: LineItem[];
  status: InvoiceStatus;
  created_at: string;
  updated_at: string;
  last_collections_message?: string;
}

export interface ListInvoicesResult {
  invoices: Invoice[];
  count: number;
  last_evaluated_key: string | null;
}

export interface ListInvoicesParams {
  status?: InvoiceStatus;
  due_before?: string;
  due_after?: string;
  limit?: number;
  last_evaluated_key?: string;
}

async function authHeader(): Promise<Record<string, string>> {
  const session = await fetchAuthSession();
  const token = session.tokens?.idToken?.toString();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: token };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(await authHeader()),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Request to ${path} failed (${response.status}): ${body}`);
  }

  return response.json() as Promise<T>;
}

export async function listInvoices(params: ListInvoicesParams = {}): Promise<ListInvoicesResult> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const qs = query.toString();
  return request<ListInvoicesResult>(`/invoices${qs ? `?${qs}` : ""}`);
}

export async function getInvoice(id: string): Promise<Invoice> {
  return request<Invoice>(`/invoices/${id}`);
}

export async function createInvoice(data: {
  client_name: string;
  client_email: string;
  amount: number;
  due_date: string;
  currency?: string;
  description?: string;
  line_items?: LineItem[];
}): Promise<Invoice> {
  return request<Invoice>("/invoices", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateInvoice(id: string, data: Partial<Invoice>): Promise<Invoice> {
  return request<Invoice>(`/invoices/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function generatePdf(
  id: string
): Promise<{ invoice_id: string; pdf_url: string; expires_in: number }> {
  const result = await request<{ invoice_id: string; pdf_url: string; expires_in: number }>(
    `/invoices/${id}/pdf`,
    { method: "POST" }
  );
  window.open(result.pdf_url, "_blank", "noopener,noreferrer");
  return result;
}

export async function generateCollectionsMessage(
  id: string
): Promise<{ invoice_id: string; days_overdue: number; message: string }> {
  return request<{ invoice_id: string; days_overdue: number; message: string }>(
    `/invoices/${id}/collect`,
    { method: "POST" }
  );
}
