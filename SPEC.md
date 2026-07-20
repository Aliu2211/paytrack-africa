# PayTrack Africa — Technical Specification

This document describes the system as built: what it does, how data is modeled, what the API contracts are, and why certain decisions were made. It's written for a human reader — a reviewer, a new contributor, or future-me — not as a task list. For "how do I run this," see [README.md](README.md).

---

## 1. Purpose and Users

PayTrack Africa is invoicing and collections software for accounting firms that manage receivables on behalf of several small-and-medium clients at once. The reference scenario used throughout development: **AgroVault Africa Ltd**, an accounting firm in Ghana serving a portfolio of SME clients, each of whom needs their own invoices tracked, reminded, and collected on — without any client seeing another client's data.

That framing drives the one non-negotiable requirement: **every piece of data belongs to exactly one tenant, and the system must make it structurally difficult to leak data across tenants** — not just filter it out in application code as an afterthought.

## 2. Multi-Tenancy Model

There is one AWS account, one set of DynamoDB tables, and one Cognito user pool shared by every tenant. Isolation is enforced at three layers, redundantly:

1. **Identity**: every Cognito user carries a `custom:tenant_id` attribute, set at account-provisioning time (self-signup is disabled in the dashboard for this reason — a self-registered account has no tenant and cannot use the API).
2. **AuthZ boundary**: API Gateway's Cognito authorizer puts that claim into `event.requestContext.authorizer.claims["custom:tenant_id"]` on every request. Every Lambda reads it from there — never from a request body or path parameter — so a client cannot simply pass a different `tenant_id` to read someone else's data.
3. **Storage**: `tenant_id` is the DynamoDB partition key on every table. A `Query` is structurally scoped to one partition; there is no code path that queries "all invoices" without a tenant key. Even `GetItem` calls use `{tenant_id, invoice_id}` as the full key — fetching another tenant's invoice by ID alone is impossible, not just disallowed.

A secondary check exists for a specific edge case: if a `GetItem` for `{tenant_id, invoice_id}` misses, the handler runs a table `Scan` filtered on `invoice_id` alone to determine whether the invoice exists under a *different* tenant, purely so it can return `403 Forbidden` instead of `404 Not Found`. That distinction matters for API consumers (and is exercised by `test_get_invoice_wrong_tenant`) but the scan result is only ever used to pick a status code, never returned to the caller.

## 3. Data Model

Three DynamoDB tables, all `PAY_PER_REQUEST`, all with point-in-time recovery enabled.

### `tenants`
| Attribute | Type | Notes |
|---|---|---|
| `tenant_id` (PK) | String (UUID) | |
| `business_name` | String | Set at provisioning time |
| `invoice_counter` | Number | Maintained by an atomic `ADD` on every invoice creation — see §4 |

### `invoices`
| Attribute | Type | Notes |
|---|---|---|
| `tenant_id` (PK) | String | |
| `invoice_id` (SK) | String | `INV-{tenant_id[:8]}-{random hex}` |
| `invoice_number` | Number | Per-tenant sequential, starts at 1 |
| `client_name`, `client_email` | String | |
| `amount` | Number (Decimal) | |
| `currency` | String | Defaults to `GHS` |
| `due_date` | String | ISO date, `YYYY-MM-DD` |
| `status` | String | `draft` \| `sent` \| `paid` \| `cancelled` — see §5 |
| `description`, `line_items` | String, List | Optional, used on the generated PDF |
| `last_collections_message` | String | Set by `ai_collections`, absent until first generated |
| `created_at`, `updated_at` | String | ISO 8601 UTC, e.g. `2026-07-20T13:04:18Z` |

DynamoDB Streams is enabled (`NEW_AND_OLD_IMAGES`) — this is what drives the `analytics` Lambda; see §7. The table also has a `ttl` attribute configured at the infrastructure level, but no handler currently writes a value to it — it's provisioned for a future auto-archival use case (e.g. purging old `cancelled` drafts) and is inert today. Worth knowing before assuming old invoices expire on their own; they don't.

A global secondary index, `status-due-date-index` (PK `tenant_id`, SK `due_date`), lets `payment_reminder` and the dashboard's due-date filters query a time window without a table scan. Despite the name, it is *not* status-keyed — status filtering happens with a `FilterExpression` after the query, since status has low cardinality and isn't worth a separate index.

### `analytics`
| Attribute | Type | Notes |
|---|---|---|
| `tenant_id` (PK) | String | |
| `metric_key` (SK) | String | `invoices_draft`, `invoices_sent`, `invoices_paid`, `invoices_cancelled`, `total_outstanding_amount` |
| `metric_value` | Number | Maintained incrementally — never recomputed from scratch |

This table holds **cumulative, current-state counters only**. It cannot answer "how many invoices were sent this week" — that would require snapshotting deltas over time, which nothing in the product currently needs (the weekly report computes that figure a different way — see §7).

## 4. Invoice Numbering

Two identifiers exist per invoice, deliberately:

- **`invoice_id`** — globally unique, used as the DynamoDB sort key and in URLs. Not shown to end users as "the" invoice number because it's not sequential or memorable.
- **`invoice_number`** — a per-tenant sequential integer (`1, 2, 3, …`), the one a business owner actually recognizes. Generated with a single atomic `UpdateItem … ADD invoice_counter :1` against the `tenants` table, which both increments the counter and creates the tenant record with counter `1` if it doesn't exist yet — so there's no separate "provision a tenant" step before the first invoice.

This is a DynamoDB counter, not an auto-increment column — it's atomic under concurrent writes (two simultaneous invoice creations for the same tenant can never receive the same number) but it does mean invoice numbers are per-tenant, not global.

## 5. Invoice Lifecycle

```
draft ──► sent ──► paid
  │
  └──────► cancelled
```

Enforced centrally in `invoice_update`'s `VALID_TRANSITIONS` set: `{(draft, sent), (draft, cancelled), (sent, paid)}`. Any other requested transition — including a no-op re-set to the same status — returns `400`. There is no "un-send" or "un-pay"; the model is intentionally one-directional, matching how real invoicing works (you don't un-ring that bell without a credit note, which is out of scope here).

`invoice_update` accepts any non-immutable field, not just `status` — `IMMUTABLE_FIELDS = {tenant_id, invoice_id, created_at}` — so due dates, amounts, or client details can be corrected on a draft without a dedicated "edit" endpoint.

## 6. API

All routes sit behind API Gateway's Cognito authorizer; every request needs a valid ID token in `Authorization`. CORS is enabled on every resource, including on API Gateway's own 4xx/5xx gateway responses (so a Lambda-level error still carries `Access-Control-Allow-Origin`, rather than surfacing to the browser as an opaque CORS failure that masks the real error).

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/invoices` | `client_name, client_email, amount, due_date` (+ optional `currency, description, line_items`) | `201` + the created invoice, `status: draft` |
| `GET` | `/invoices` | — (query: `status`, `due_before`, `due_after`, `limit`, `last_evaluated_key`) | `200` + `{invoices, count, last_evaluated_key}`, cursor-paginated |
| `GET` | `/invoices/{id}` | — | `200` + invoice, or `403`/`404` |
| `PUT` | `/invoices/{id}` | any non-immutable field | `200` + updated invoice, or `400` on an invalid status transition |
| `POST` | `/invoices/{id}/collect` | — | `200` + `{invoice_id, days_overdue, message}` — a Gemini-generated collections message |
| `POST` | `/invoices/{id}/pdf` | — | `200` + `{invoice_id, pdf_url, expires_in}` — `pdf_url` is a 24h presigned S3 URL |

Every handler returns the same shape on failure: `{"message": "..."}` with an appropriate status code (`400` malformed input, `403` wrong tenant or no tenant assigned, `404` not found).

## 7. Background Processing

Three Lambdas run outside the request/response cycle:

**`payment_reminder`** — EventBridge cron, `0 8 * * ? *` (8am UTC = 8am Ghana time, no DST). Scans all tenants, queries each one's `sent` invoices due within the next 3 days via `status-due-date-index`, and for each one publishes to an SNS topic *and* sends the client a reminder email via SES. Returns `{total_scanned, total_reminded, reminded_invoice_ids}` for testability and CloudWatch log inspection.

**`ai_collections`** — synchronous, called from the dashboard. Computes `days_overdue = today − due_date` and picks a tone:

| Days overdue | Tone |
|---|---|
| < 14 | firm but polite |
| 14–29 | urgent |
| ≥ 30 | final notice |

The prompt to Gemini (`gemini-flash-latest`) asks for a 3-sentence professional message given the tone, client name, invoice number, and amount. The result is saved onto the invoice (`last_collections_message`) and returned to the caller. The Gemini call is isolated in a single function (`_generate_collections_message`) specifically so tests can monkeypatch that one call point — unit tests verify the tone-selection logic, not the model's prose, and never hit the network.

**`analytics`** — DynamoDB Streams-triggered off the `invoices` table (`starting_position: LATEST`). For each `INSERT`/`MODIFY` record, it decodes the `NewImage`/`OldImage` low-level attribute values and, if `status` changed, atomically decrements the old status counter and increments the new one (`ADD metric_value :delta` against the `analytics` table). `total_outstanding_amount` is maintained the same way: added when an invoice enters `sent`, subtracted when it leaves `sent`. A `MODIFY` where status didn't change (e.g. a description edit) is a no-op — the handler only acts when `old_status != new_status`. This means the counters are always live and there's no polling or scheduled recomputation involved.

**`weekly_report`** — EventBridge cron, `0 9 ? * MON *` (Monday 9am Ghana time). For each tenant: queries their invoices directly and filters by `updated_at`/`due_date` in Python to get *this week's* sent/paid counts and the overdue count (the `analytics` table can't answer "this week" questions — see §3 — so this Lambda goes to the source of truth instead), reads `total_outstanding_amount` from the `analytics` table since that figure genuinely is a current-state snapshot, and emails a plain-text summary via SES. Tenant contact info comes from Cognito: `ListUsers` can't filter on custom attributes server-side, so the Lambda lists every user in the pool once and matches `custom:tenant_id` in code — acceptable at the scale of an accounting firm's client list, not something that would survive to a pool with millions of users.

## 8. Infrastructure

Terraform, one root module wiring together: `dynamodb`, `cognito`, `lambda`, `api_gateway`, `s3_pdf`, `sns`, `ses`, `eventbridge`, `cloudwatch`, `github_oidc`. Every Lambda shares one IAM execution role with scoped inline policies (DynamoDB tables it actually needs, the Gemini secret, the invoices stream, SES/SNS, X-Ray) rather than a broad managed policy.

Lambda deployment packages are built by `scripts/package_lambdas.sh` and uploaded to S3, not inlined directly into the Terraform resource — a 33MB package (reportlab's compiled dependencies) hit `InvalidSignatureException` on direct inline upload over a slow connection. The packaging script also normalizes file mtimes, strips `__pycache__`, and sorts the file list before zipping, so identical source produces a byte-identical zip on every run; without that, `terraform plan` treated every Lambda as changed on every apply regardless of whether its code actually did.

CI/CD (`.github/workflows/deploy.yml`) authenticates to AWS via GitHub's OIDC provider — a short-lived assumed role, no static AWS keys stored in GitHub. The trust policy's `sub` condition has to account for GitHub's actual claim format, which inlines numeric owner/repo IDs (`repo:OWNER@id/REPO@id:ref:refs/heads/main`) rather than the plain-name format shown in most documentation examples.

## 9. Observability

Every Lambda has two CloudWatch alarms (error count ≥ 5 in 5 minutes, P95 duration ≥ 3s), both wired to an SNS topic with an email subscription. API Gateway has 4xx/5xx *rate* alarms computed via metric math (`errors / requests * 100`), not raw counts, so alarm sensitivity doesn't depend on traffic volume. X-Ray tracing is on for both API Gateway and every Lambda, giving a single trace across the full request path. A CloudWatch dashboard aggregates invocation counts, error counts, P95 duration per function, and API Gateway request/latency metrics into one view.

## 10. Testing Strategy

23 tests, all `moto`-mocked — no AWS account required to run them. The philosophy: test business logic and tenant-isolation guarantees, not AWS itself.

- `test_invoice_api.py` (12 tests) — CRUD, status transitions, cross-tenant access attempts, pagination.
- `test_reminder_pipeline.py` (6 tests) — reminder scanning/filtering, PDF generation, AI message tone selection (Gemini call monkeypatched).
- `test_analytics.py` (5 tests) — synthetic DynamoDB Streams records asserting counter increment/decrement behavior, plus a `weekly_report` smoke test against a moto-mocked Cognito pool matching the real schema.

## 11. Known Limitations

- **SES sandbox mode**: both sender and every recipient must be individually verified until AWS grants production access. This is an AWS account posture, not a code limitation — `payment_reminder` and `weekly_report` are unit-tested and have been invoked live successfully against verified addresses.
- **Single AWS region, single account, single environment (`dev`)**: no multi-region failover, no separate staging environment. Reasonable for the current scale; would need addressing before onboarding a paying customer with an SLA.
- **`weekly_report`'s Cognito `ListUsers` scan**: fine at SME-accounting-firm scale (dozens to low hundreds of client accounts), would need a different lookup strategy (e.g. a GSI on a DynamoDB table mirroring tenant contacts) at real scale.
- **No credit notes / invoice reversal**: the status state machine is intentionally one-directional; correcting a paid or cancelled invoice today means creating a new one.
