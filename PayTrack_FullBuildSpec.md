# PayTrack Africa — Complete Project Build Specification
**Phases 1 through 5 — All Modules, All Specs**

> Claude Code Build Document | Aliu Tijani | July 2026

| Field | Value |
|---|---|
| Client | AgroVault Africa Ltd (simulated) — Accounting firm serving Ghanaian SMEs |
| Product | AI-powered invoice and payment tracking SaaS platform |
| Architecture | Multi-tenant serverless — each SME is a completely isolated tenant |
| Stack | AWS Lambda (Python 3.12), API Gateway, DynamoDB, Cognito, S3, SNS, EventBridge, SES, Terraform, GitHub Actions |
| Region | us-east-1 |
| Developer | Aliu Tijani — aliutijani21@gmail.com |

---

## Global Rules for Claude Code

These rules apply to every phase and every step. Never violate them regardless of what a step says.

- **Tenant isolation is non-negotiable.** Every Lambda handler must extract `tenant_id` from Cognito claims and use it as the DynamoDB partition key. A request from tenant A must never return or modify tenant B data.
- **Infrastructure as Code only.** No manual console clicks for any infrastructure. Everything in Terraform.
- **Least privilege IAM.** Lambda roles get only the permissions they need on the specific resources they use. No wildcard resources.
- **Stop at every STOP AND REPORT checkpoint.** Do not proceed to the next step or phase until explicitly cleared.
- **No partial builds.** Complete each step fully before moving to the next. Do not skip ahead.
- **No em dashes** in any generated prose, comments, or documentation.

---

## Complete Project Structure

Create this full directory tree at the start of Phase 1. Phases 2 through 5 will add to it without changing the structure established here.

```
paytrack-africa/
├── infrastructure/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── providers.tf
│   ├── backend.tf                   (empty until Step 11)
│   ├── packages/
│   │   └── .gitkeep
│   └── modules/
│       ├── dynamodb/
│       ├── lambda/
│       ├── api_gateway/
│       ├── cognito/
│       ├── eventbridge/              (Phase 2)
│       ├── sns/                      (Phase 2)
│       ├── ses/                      (Phase 2)
│       └── cloudwatch/               (Phase 3)
├── functions/
│   ├── invoice_create/
│   ├── invoice_get/
│   ├── invoice_list/
│   ├── invoice_update/
│   ├── payment_reminder/             (Phase 2)
│   ├── invoice_pdf/                  (Phase 2)
│   ├── ai_collections/               (Phase 2)
│   └── analytics/                    (Phase 5)
├── dashboard/                        (Phase 4 — Next.js frontend)
│   ├── pages/
│   ├── components/
│   └── public/
├── .github/workflows/
│   └── deploy.yml
├── scripts/
│   └── package_lambdas.sh
├── tests/
│   ├── test_invoice_api.py
│   ├── test_reminder_pipeline.py     (Phase 2)
│   └── test_analytics.py             (Phase 5)
├── .gitignore
└── README.md
```

`.gitignore` must include:
```
infrastructure/packages/*.zip
.terraform/
*.tfstate
*.tfstate.backup
.terraform.lock.hcl
__pycache__/
*.pyc
.env
dashboard/.next/
dashboard/node_modules/
```

---

# Phase 1: Core Infrastructure and Invoice API
**Weeks 1 to 2 | New skills: Multi-tenant DynamoDB, Cognito auth, API Gateway, Terraform modules**

### What Phase 1 Builds
- Terraform modules: DynamoDB (2 tables), Cognito (user pool and client), Lambda (4 functions), API Gateway (REST API with Cognito authorizer)
- 4 Lambda handlers: invoice_create, invoice_get, invoice_list, invoice_update
- Remote state: S3 bucket and DynamoDB lock table
- GitHub Actions CI/CD pipeline: test then deploy
- 12 moto-mocked unit tests covering CRUD and tenant isolation

---

## Step 1: providers.tf

```hcl
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}
provider "aws" { region = var.aws_region }
```

## Step 2: variables.tf

Variables required:
- `aws_region` (string, default `us-east-1`)
- `environment` (string, default `dev`)
- `project_name` (string, default `paytrack`)
- `state_bucket_name` (string, no default — required)
- `cognito_user_pool_name` (string, default `paytrack-sme-users`)

## Step 3: DynamoDB Module

**Table 1: `paytrack-tenants-{environment}`**
- Partition key: `tenant_id` (String)
- Billing: PAY_PER_REQUEST, PITR enabled

**Table 2: `paytrack-invoices-{environment}`**
- Partition key: `tenant_id` (String), sort key: `invoice_id` (String)
- GSI: `status-due-date-index` (PK: `tenant_id`, SK: `due_date`, projection ALL)
- TTL attribute: `ttl`, PITR enabled

Outputs: `tenants_table_name`, `tenants_table_arn`, `invoices_table_name`, `invoices_table_arn`

## Step 4: Cognito Module

- User pool: email as username, email auto-verified, 8-char password with uppercase/lowercase/numbers
- Custom schema attributes: `tenant_id` (String, mutable), `business_name` (String, mutable)
- Client: `ALLOW_USER_PASSWORD_AUTH`, `ALLOW_USER_SRP_AUTH`, and `ALLOW_REFRESH_TOKEN_AUTH`, no secret, 1hr access token, 30 day refresh. `ALLOW_USER_SRP_AUTH` is required for the Phase 4 frontend -- AWS Amplify's `Authenticator` component signs in via SRP by default, not plain `USER_PASSWORD_AUTH`, and the sign-in fails with `USER_SRP_AUTH is not enabled for the client` without it.

Outputs: `user_pool_id`, `user_pool_arn`, `user_pool_client_id`, `user_pool_endpoint`

## Step 5: Lambda Module

**IAM Role**
- Trust: `lambda.amazonaws.com`, attach `AWSLambdaBasicExecutionRole`
- Inline policy: PutItem, GetItem, UpdateItem, Query, Scan on both table ARNs from dynamodb module outputs

**Four Lambda Functions (all share these settings)**
- Runtime `python3.12`, handler `handler.lambda_handler`, memory 256MB, timeout 30s
- Env vars: `INVOICES_TABLE`, `TENANTS_TABLE`, `ENVIRONMENT` (all from module inputs)
- Filename: `${path.module}/../../packages/{function_name}.zip`, `source_code_hash` from `filebase64sha256`. Use `path.module`, not a bare relative path — Terraform resolves bare relative paths against the invocation CWD, not the module's directory, so a literal `../packages/...` breaks once the Lambda resource lives inside a `modules/lambda/` submodule two levels below `infrastructure/`.

Outputs: ARN and name of each function

## Step 6: API Gateway Module

```
/invoices          POST -> invoice_create,  GET -> invoice_list
/invoices/{id}     GET  -> invoice_get,     PUT -> invoice_update
```

- All methods: COGNITO_USER_POOLS auth, AWS_PROXY integration, POST integration method
- Authorizer: `method.request.header.Authorization`, references Cognito user pool ARN
- Deployment: `depends_on` all integrations, `triggers` block with sha1, `create_before_destroy` lifecycle
- Lambda permissions: `apigateway.amazonaws.com` can invoke each function
- **CORS**: add an `OPTIONS` method (MOCK integration) on every resource returning `Access-Control-Allow-Origin`/`-Methods`/`-Headers`, and set `Access-Control-Allow-Origin` on every Lambda's actual JSON response headers (not just the preflight). This wasn't needed until Phase 4's browser-based frontend existed -- `curl`-based testing in Phases 1-3 never triggers CORS since it isn't a browser, so the gap went unnoticed until the dashboard's `fetch()` calls failed with "Failed to fetch."

Outputs: `api_id`, `api_url` (full invoke URL with stage)

## Step 7: Root main.tf and outputs.tf

Module call order:
1. `dynamodb` and `cognito` (no deps)
2. `lambda` (needs dynamodb ARNs)
3. `api_gateway` (needs lambda ARNs and cognito ARN)

Root outputs: `api_url`, `cognito_user_pool_id`, `cognito_client_id`, `invoices_table_name`, `tenants_table_name`

> **STOP AND REPORT** — Run `terraform init` and `terraform validate`. Report full output before writing Lambda handlers.

## Step 8: Lambda Handler Code

**All handlers must follow this pattern:**
1. Extract `tenant_id` from `event['requestContext']['authorizer']['claims']['custom:tenant_id']`
2. Validate required fields, return 400 if missing
3. Perform DynamoDB operation
4. Return `{statusCode, body: json.dumps(...)}` API Gateway proxy response

### invoice_create — POST /invoices
- Required body: `client_name`, `client_email`, `amount`, `due_date`
- Optional: `currency` (default GHS), `description`, `line_items`
- `invoice_id`: `INV-{tenant_id[:8].upper()}-{uuid4().hex[:8].upper()}`
- `invoice_number`: Atomic counter, not a COUNT query (avoids duplicate numbers under concurrent creates). Maintain a counter item on the tenant record (e.g. `paytrack-tenants` item with `sk=COUNTER#invoice`) and increment it with `UpdateItem` using `ADD invoice_number :incr`, `ConditionExpression` not required since `ADD` on a missing attribute initializes it. Use the returned `ALL_NEW` value.
- `status`: `draft`, `created_at` and `updated_at`: `datetime.utcnow().isoformat() + 'Z'`
- Return 201 with created invoice

### invoice_get — GET /invoices/{invoice_id}
- `get_item` with Key `{tenant_id, invoice_id}`
- Not found: 404. Tenant mismatch: 403. Found: 200

### invoice_list — GET /invoices
- Optional params: `status`, `due_before`, `due_after`, `limit` (default 20 max 100), `last_evaluated_key`
- Use GSI if `due_before` or `due_after` provided, else query main table
- Return `{invoices, count, last_evaluated_key}` (last_evaluated_key base64 encoded or null)

### invoice_update — PUT /invoices/{invoice_id}
- First verify invoice exists and belongs to tenant (404 or 403 if not)
- Reject updates to `tenant_id`, `invoice_id`, `created_at`: return 400
- Valid status transitions: `draft` to `sent`, `draft` to `cancelled`, `sent` to `paid` only
- Dynamic UpdateExpression from fields present in body, always update `updated_at`
- `ConditionExpression` ensures `tenant_id` matches
- Return 200 with updated invoice

All four `requirements.txt` files contain only: `boto3`

> **STOP AND REPORT** — All four handlers written and reviewed before continuing.

## Step 9: Packaging Script

```bash
#!/bin/bash
set -e
FUNCTIONS=(invoice_create invoice_get invoice_list invoice_update)
mkdir -p infrastructure/packages
for FUNC in ${FUNCTIONS[@]}; do
  cd functions/$FUNC
  pip install -r requirements.txt -t ./package --quiet
  cp handler.py ./package/
  cd package && zip -r ../../../infrastructure/packages/${FUNC}.zip . --quiet
  cd .. && rm -rf package && cd ../..
done
echo "All packages created."
```

> **STOP AND REPORT** — Run `bash scripts/package_lambdas.sh` and confirm 4 zip files exist in `infrastructure/packages/`.

## Step 10: GitHub Actions CI/CD

- Trigger: push and pull_request to `main`
- Job 1 (test): setup Python 3.12, `pip install pytest boto3 moto`, run `pytest tests/ -v`
- Job 2 (deploy): needs test, only on main — configure AWS creds, package Lambdas, `terraform init`, `plan`, `apply`
- Secrets required: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `TF_STATE_BUCKET` (value: `paytrack-tf-state-2026`)

## Step 11: Bootstrap Remote State and First Deploy

```bash
# Create state bucket
aws s3 mb s3://paytrack-tf-state-2026 --region us-east-1
aws s3api put-bucket-versioning \
  --bucket paytrack-tf-state-2026 \
  --versioning-configuration Status=Enabled

# Create DynamoDB lock table
aws dynamodb create-table \
  --table-name paytrack-tf-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Now write `infrastructure/backend.tf`:
```hcl
terraform {
  backend "s3" {
    bucket         = "paytrack-tf-state-2026"
    key            = "paytrack/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "paytrack-tf-lock"
  }
}
```

```bash
cd infrastructure && terraform init   # type yes to migrate state
terraform plan -var="state_bucket_name=paytrack-tf-state-2026"
terraform apply -var="state_bucket_name=paytrack-tf-state-2026"
```

> **STOP AND REPORT** — `terraform apply` must complete with zero errors. Paste full Outputs block.

## Step 12: Phase 1 Tests

Write `tests/test_invoice_api.py` using `moto`. Required test cases:

- `test_create_invoice_success`: valid payload returns 201 with `invoice_id`, `invoice_number`, `status=draft`
- `test_create_invoice_missing_amount`: returns 400
- `test_create_invoice_missing_client_name`: returns 400
- `test_get_invoice_success`: tenant A retrieves own invoice
- `test_get_invoice_wrong_tenant`: tenant B gets 403 on tenant A invoice
- `test_get_invoice_not_found`: returns 404
- `test_list_invoices_empty`: returns `{invoices: [], count: 0}`
- `test_list_invoices_own_tenant_only`: tenant A cannot see tenant B invoices
- `test_list_invoices_pagination`: 25 invoices, limit=10 returns 10 + `last_evaluated_key`
- `test_update_status_draft_to_sent`: succeeds
- `test_update_status_invalid_transition`: sent to draft returns 400
- `test_update_wrong_tenant`: returns 403

> **STOP AND REPORT** — All 12 tests pass with `pytest tests/ -v`. Paste full pytest output. **Phase 1 is complete.**

---

# Phase 2: Payment Reminder Pipeline and AI Collections
**Weeks 3 to 4 | New skills: EventBridge, SNS, SES, Gemini in Lambda, PDF generation with reportlab**

### What Phase 2 Builds
- EventBridge scheduled rule: triggers daily at 8am Ghana time (`cron(0 8 * * ? *)`)
- Payment reminder Lambda: scans invoices due in next 3 days, sends SMS via SNS
- AI collections Lambda: given invoice + days overdue, calls Gemini to generate contextual message
- PDF invoice Lambda: generates PDF with `reportlab`, stores in S3, returns presigned URL
- SES email configuration for reminder emails as fallback to SMS

## Step 1: New Terraform Modules

**SNS Module**
- Topic: `paytrack-payment-reminders-{environment}`
- Output: `topic_arn`

**SES Module**
- SES email identity for sending (configure domain or verified email)
- IAM policy allowing Lambda to call `ses:SendEmail`

**EventBridge Module**
- Rule: `paytrack-daily-reminder-{environment}`, schedule `cron(0 8 * * ? *)`
- Target: `payment_reminder` Lambda function
- Lambda permission allowing `events.amazonaws.com` to invoke the function

## Step 2: Update Lambda IAM Role

Add to the existing Lambda IAM role inline policy:
- `sns:Publish` on the reminders topic ARN
- `ses:SendEmail` on `*` (SES does not support resource-level ARNs for `SendEmail`)
- `s3:PutObject` and `s3:GetObject` on the new `paytrack-invoices-pdf-{environment}` S3 bucket
- `secretsmanager:GetSecretValue` on the Gemini API key secret ARN

## Step 3: New S3 Bucket for PDFs

- Bucket: `paytrack-invoices-pdf-{environment}`
- Public access blocked, CORS allowing GET from `*`
- Lifecycle rule: expire objects after 7 days

## Step 4: Store Gemini API Key in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name paytrack/gemini-api-key \
  --secret-string '{"api_key": "YOUR-GEMINI-KEY-HERE"}' \
  --region us-east-1
```

Add a Terraform `data` source to reference this secret ARN in Lambda environment and IAM policy.

## Step 5: payment_reminder Lambda

- Triggered by EventBridge daily at 8am Ghana time
- The `status-due-date-index` GSI is keyed per tenant (`PK: tenant_id`, `SK: due_date`), so it cannot be queried across all tenants in one call. Two-step scan:
  1. `Scan` the tenants table (small, bounded by SME client count) to collect all `tenant_id`s
  2. For each tenant, `Query` `status-due-date-index` with `KeyConditionExpression` on `tenant_id` and `due_date BETWEEN today AND today+3`, then filter results in code for `status=sent`
- For each matching invoice: publish to SNS topic with client name, amount, due date, invoice number
- Also send email via SES to the client email on the invoice
- Log summary: total scanned, total reminded
- `requirements.txt`: `boto3`

## Step 6: ai_collections Lambda

- Triggered via POST `/invoices/{invoice_id}/collect` (new API Gateway route — add in Terraform)
- Read invoice from DynamoDB (same tenant isolation pattern)
- Calculate `days_overdue` from `due_date` to today
- Fetch Gemini API key from Secrets Manager
- Call Gemini (`gemini-flash-latest` -- an alias, not a pinned version, since specific Gemini model IDs get deprecated for new API keys without notice) with this prompt logic:
  - Under 14 days overdue: firm but polite
  - 14 to 30 days overdue: urgent
  - Over 30 days: final notice
  - Max 3 sentences, professional English
- Store generated message on invoice in DynamoDB as `last_collections_message`
- Return 200 with `{invoice_id, days_overdue, message}`
- `requirements.txt`: `boto3 google-genai`

## Step 7: invoice_pdf Lambda

- Triggered via POST `/invoices/{invoice_id}/pdf` (new API Gateway route)
- Read invoice from DynamoDB
- Generate PDF using `reportlab`: company header, invoice number, client details, line items table, total, due date, payment footer
- Upload to S3 at key `{tenant_id}/{invoice_id}.pdf`
- Generate presigned URL valid for 24 hours
- Return 200 with `{invoice_id, pdf_url, expires_in: 86400}`
- `requirements.txt`: `boto3 reportlab`

> **STOP AND REPORT** — All three new Lambda functions deployed and tested manually via curl with a JWT token.

## Step 8: Phase 2 Tests

Write `tests/test_reminder_pipeline.py` using `moto`. Required test cases:

- `test_reminder_scans_correct_invoices`: only sent invoices due in next 3 days are included
- `test_reminder_skips_paid_invoices`: paid invoices are not reminded
- `test_reminder_skips_draft_invoices`: draft invoices are not reminded
- `test_pdf_generates_and_uploads`: PDF bytes uploaded to S3 and presigned URL returned
- `test_collections_message_low_urgency`: message generated for 5 days overdue contains polite tone
- `test_collections_message_high_urgency`: message generated for 45 days overdue is escalated

> **STOP AND REPORT** — All Phase 2 tests pass. Paste pytest output. **Phase 2 is complete.**

---

# Phase 3: Monitoring, Alerting, and CloudWatch
**Weeks 5 to 6 | New skills: CloudWatch alarms, SNS alert routing, dashboard metrics, X-Ray tracing**

### What Phase 3 Builds
- CloudWatch alarms for each Lambda: error rate above 5% and P95 duration above 3 seconds
- SNS alert topic for engineering notifications when alarms fire
- CloudWatch dashboard showing real-time metrics for all Lambda functions and API Gateway
- X-Ray tracing enabled on all Lambda functions
- Structured JSON logging from all Lambda handlers

## Step 1: CloudWatch Module

**SNS Alert Topic**
- Topic: `paytrack-engineering-alerts-{environment}`
- Email subscription (provide engineering email as Terraform variable)

**CloudWatch Alarms — create for each Lambda function**
- Error rate alarm: metric `Errors`, period 300s, threshold 5, treat missing data as `notBreaching`
- Duration alarm: metric `Duration`, extended statistic `p95`, period 300s, threshold 3000ms
- All alarms: `alarm_actions = [engineering_alerts_topic_arn]`

**API Gateway Alarms**
- 4xx error rate: greater than 10% over 5 minutes
- 5xx error rate: greater than 1% over 5 minutes

## Step 2: CloudWatch Dashboard

Create a dashboard named `paytrack-{environment}` with these widgets:
- Lambda invocations line graph: all functions, 1 hour window
- Lambda error count bar graph: all functions, 1 hour window
- Lambda P95 duration line graph: all functions, 1 hour window
- API Gateway 4xx count, 5xx count, latency P95: 1 hour window each

## Step 3: Enable X-Ray Tracing

In the Lambda Terraform module, add `tracing_config { mode = PassThrough }` to all Lambda functions. Add `xray:PutTraceSegments` and `xray:PutTelemetryRecords` to the Lambda IAM role.

## Step 4: Structured Logging

Update all Lambda handlers to log structured JSON at start and end of each invocation:

```python
import json, logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.info(json.dumps({
    "event": "invoke",
    "function": "invoice_create",
    "tenant_id": tenant_id,
    "request_id": context.aws_request_id
}))
```

> **STOP AND REPORT** — All alarms created, dashboard visible in CloudWatch console, X-Ray traces appearing. **Phase 3 is complete.**

---

# Phase 4: Next.js Dashboard Frontend
**Weeks 7 to 8 | New skills: Next.js with AWS Cognito auth, Amplify hosting, real-time dashboard**

### What Phase 4 Builds
- Next.js 14 frontend in the `dashboard/` directory
- Cognito authentication using AWS Amplify Auth
- Invoice list page with search, filter by status, and pagination
- Invoice detail page with PDF download and AI collections message trigger
- Create invoice form with validation
- Analytics page showing outstanding receivables by status
- Deployed to AWS Amplify or S3 + CloudFront

## Step 1: Initialise Next.js Project

```bash
cd dashboard
npx create-next-app@latest . --typescript --tailwind --app
npm install aws-amplify @aws-amplify/ui-react
```

## Step 2: Cognito Auth Configuration

Create `dashboard/src/lib/auth.ts` configuring Amplify with:
- `UserPoolId` from Terraform output `cognito_user_pool_id`
- `UserPoolClientId` from Terraform output `cognito_client_id`
- Region: `us-east-1`

Wrap the root layout with Amplify Authenticator so all pages require login.

## Step 3: API Client

Create `dashboard/src/lib/api.ts` with typed functions:
- `listInvoices(params)`: GET `/invoices` with auth header
- `getInvoice(id)`: GET `/invoices/{id}`
- `createInvoice(data)`: POST `/invoices`
- `updateInvoice(id, data)`: PUT `/invoices/{id}`
- `generatePdf(id)`: POST `/invoices/{id}/pdf`, opens presigned URL in new tab
- `generateCollectionsMessage(id)`: POST `/invoices/{id}/collect`

## Step 4: Pages

**`/invoices` — Invoice List**
- Table: `invoice_number`, `client_name`, `amount`, `currency`, `status`, `due_date`
- Status filter dropdown, search by client name, pagination with `last_evaluated_key`
- Create Invoice button opens modal form

**`/invoices/[id]` — Invoice Detail**
- All invoice fields, status badge colour coding: draft=grey, sent=blue, paid=green, cancelled=red
- Update Status button (shows valid transitions only)
- Download PDF button, Generate Collections Message button (shows result inline)

**`/analytics` — Analytics**
- Cards: total invoices, total outstanding amount, total paid this month, overdue count
- Bar chart of invoices by status

## Step 5: Deploy Frontend

**Option A (Amplify):** Connect GitHub repo to AWS Amplify, build command `cd dashboard && npm run build`, output `dashboard/.next`

**Option B (S3 + CloudFront):** Run `next export`, sync to S3 bucket, create CloudFront distribution

> **STOP AND REPORT** — Frontend deployed, login with Cognito works, invoice list populates from the real API. **Phase 4 is complete.**

---

# Phase 5: Analytics Pipeline and Portfolio Polish
**Weeks 9 to 10 | New skills: DynamoDB Streams, EventBridge Pipes, scheduled SES reports**

### What Phase 5 Builds
- DynamoDB Streams on invoices table to track every status change
- Analytics Lambda: triggered by stream, updates summary record per tenant
- Weekly report Lambda: emails summary to each tenant every Monday at 9am Ghana time
- Portfolio documentation: README, architecture diagram, video walkthrough script
- Final destroy and redeploy validation under 10 minutes

## Step 1: Enable DynamoDB Streams

In the DynamoDB Terraform module, add `stream_enabled = true` and `stream_view_type = "NEW_AND_OLD_IMAGES"` to the invoices table. Output: `invoices_stream_arn`.

## Step 2: Analytics Lambda

- Triggered by DynamoDB Stream (`aws_lambda_event_source_mapping` in Terraform)
- For each stream record: extract `tenant_id` and `status` from new image
- Update `paytrack-analytics-{environment}` DynamoDB table with counts per tenant by status
- Analytics table schema: PK `tenant_id`, SK `metric_key` (e.g. `invoices_sent`, `invoices_paid`, `total_outstanding_amount`)
- IAM additions: `GetRecords`, `GetShardIterator`, `DescribeStream`, `ListStreams` on stream ARN
- `requirements.txt`: `boto3`

## Step 3: Weekly Report Lambda

- EventBridge rule: `cron(0 9 ? * MON *)` — 9am Ghana time every Monday
- Scan analytics table for all tenants
- For each tenant: query Cognito for email and `business_name`
- Compose plain text summary: invoices sent this week, invoices paid, outstanding amount, overdue count
- Send via SES to tenant email
- `requirements.txt`: `boto3`

## Step 4: Analytics Table in Terraform

- Table: `paytrack-analytics-{environment}`
- PK: `tenant_id` (String), SK: `metric_key` (String)
- PAY_PER_REQUEST, PITR enabled
- Lambda IAM additions: PutItem, GetItem, UpdateItem, Query on analytics table ARN

## Step 5: Portfolio Documentation

**README.md** — Cover: project overview, architecture description, AWS services used and why, how to deploy from scratch under 10 minutes, how to run tests, environment variables required, lessons learned.

**Architecture Diagram** — Include a text diagram in the README showing data flow:
```
Client request -> API Gateway -> Cognito authorizer -> Lambda -> DynamoDB
EventBridge -> payment_reminder Lambda -> SNS -> SMS
EventBridge -> weekly_report Lambda -> SES -> Email
DynamoDB Stream -> analytics Lambda -> analytics table
```

**Video Walkthrough Script** — 3 to 5 minute script: what PayTrack Africa solves, live demo of creating an invoice, updating status, generating a PDF, triggering AI collections message, showing CloudWatch dashboard with real metrics.

## Step 6: Final Validation

```bash
# Destroy everything
cd infrastructure
terraform destroy -var="state_bucket_name=paytrack-tf-state-2026"

# Redeploy from scratch
bash ../scripts/package_lambdas.sh
terraform apply -var="state_bucket_name=paytrack-tf-state-2026"
```

> **STOP AND REPORT** — Full environment destroyed and redeployed in under 10 minutes. All 18+ tests pass. README complete. **Phase 5 and the full project are complete.**

---

# Full Project Acceptance Criteria

## Phase 1
- 12 unit tests pass
- `terraform apply` deploys all 5 outputs with zero errors
- Tenant isolation verified: tenant A token cannot access tenant B invoices
- GitHub Actions CI/CD green on push to main

## Phase 2
- 6 reminder pipeline tests pass
- PDF generation returns a working presigned URL
- AI collections message generated and stored on invoice in DynamoDB
- EventBridge rule configured to fire at 8am Ghana time

## Phase 3
- CloudWatch alarms exist for all Lambda functions
- CloudWatch dashboard visible with all 6 widgets
- X-Ray traces appear for test invocations
- Structured JSON logs visible in CloudWatch Logs

## Phase 4
- Frontend loads at the deployed URL
- Cognito login works and redirects to invoice list
- Invoice list, detail, create, and analytics pages all work end to end
- PDF download opens in new tab from presigned URL
- AI collections message appears inline after button click

## Phase 5
- DynamoDB stream triggers analytics Lambda on invoice status change
- Analytics table updated correctly after each status change
- Weekly report Lambda sends correctly formatted email via SES
- Full destroy and redeploy completes in under 10 minutes
- README sufficient for a junior developer to understand and deploy the system

---

# How to Use This Document

Open a Claude Code session. Upload or paste this document. Say:

> "Read this build specification document and follow it exactly, starting with Phase 1 Step 1. Stop at every STOP AND REPORT checkpoint before continuing."

When you hit a STOP AND REPORT checkpoint, paste the output before proceeding. When Phase 1 is complete, continue in the same Claude Code session with Phase 2 Step 1. If a session ends, start a new one, show it this document, and tell it which step you are on and what has already been built.

---

*PayTrack Africa | Complete Build Spec | Aliu Tijani | July 2026*
