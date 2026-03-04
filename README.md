# ai102-week1-secure-starter

## Purpose

Baseline for securely provisioning and calling Azure AI services — built as a study companion for the AI-102 exam.

## Architecture

<!-- TODO: Add architecture diagram (Saturday) -->

*Placeholder — architecture diagram coming soon.*

## Setup

<!-- Prerequisites, how to run, dependencies -->

## Auth

<!-- Key-based vs Entra ID (Azure AD) authentication comparison — Wednesday -->

### Option A — API Key

- Two keys provided per resource for zero-downtime rotation
- Passed via `Ocp-Apim-Subscription-Key` header (REST) or client constructor (SDK)
- Keys stored in Key Vault (`ai102-kvt-eus`), never in code or config files
- Rotate by regenerating Key 2, updating Key Vault, switching consumers, then regenerating Key 1

**When to use:** Dev/test, quick prototyping, scripts without identity infrastructure.

### Option B — Entra ID + Managed Identity

- No secrets to manage — identity is tied to the Azure resource (VM, App Service, Function, etc.)
- Requires custom subdomain on the AI Services resource
- Access scoped via RBAC role: `Cognitive Services User` (call APIs) or `Cognitive Services Contributor` (manage + call)
- Token acquired automatically via `DefaultAzureCredential` (SDK) or token endpoint (REST)

**When to use:** Production, CI/CD pipelines, any scenario where the exam says "most secure" or "managed identity."

### Comparison

| | API Key | Entra ID + Managed Identity |
|---|---------|---------------------------|
| Setup complexity | Low | Medium (RBAC assignment needed) |
| Secret management | Key Vault required | None — no secrets |
| Rotation | Manual (two-key swap) | Automatic (token-based) |
| Granularity | Full access per key | RBAC role-scoped |
| Custom subdomain | Optional | Required |

### Secrets Strategy

- All keys and connection strings stored in `ai102-kvt-eus`
- Application code reads from Key Vault at runtime (SDK: `SecretClient`, REST: Key Vault API)
- No secrets in environment variables, app settings, or source control
- Key Vault access via managed identity when possible, access policy or RBAC for local dev

## Monitoring

<!-- Metrics, logging, cost tracking — Thursday -->

### Diagnostic Settings

AI Services resource (`ai102-cog-eus`) sends logs and metrics to Log Analytics (`ai102-law-eus`).

| Log category | What it captures | Why it matters |
|---|---|---|
| `Audit` | Control plane operations (key regeneration, access policy changes) | Security auditing |
| `RequestResponse` | Each API call: endpoint, status code, latency, token count | Performance and usage tracking |
| `Trace` | Detailed execution traces | Debugging failed calls |

Enable all three categories in diagnostic settings. In Terraform this maps to `azurerm_monitor_diagnostic_setting` attached to the cognitive account.

### Metrics to Track

| Metric | Source | What to watch |
|---|---|---|
| Total Calls | Azure Monitor | Baseline throughput; spot unexpected spikes or drops |
| Successful Calls | Azure Monitor | Should track close to Total Calls |
| Total Errors | Azure Monitor | Sudden increases → auth issues, bad requests, or service problems |
| Latency | Azure Monitor | p50 and p95; degradation may indicate throttling or region issues |
| Server Errors (5xx) | Azure Monitor | Service-side failures — not your fault, but you need to handle them |
| Client Errors (4xx) | Azure Monitor | Bad requests, auth failures, quota exceeded (429) |
| Token Usage | RequestResponse logs | Relevant for OpenAI models; controls cost directly |

### Alert Rules

| Condition | Threshold | Action |
|---|---|---|
| Error rate spike | > 5% of total calls over 5 min | Email notification |
| Consecutive 429s (throttled) | > 10 in 5 min | Email + review quota/tier |
| Latency degradation | p95 > 2x baseline over 15 min | Investigate region or service health |
| Budget threshold hit | 80% of monthly budget | Email + evaluate usage |

### Logging Hygiene — What NOT to Log

| Do not log | Why |
|---|---|
| API keys or tokens | Credential exposure risk |
| Raw request bodies containing user input | May contain PII (names, emails, addresses, health data) |
| Raw response bodies with generated content | May reflect or amplify PII from input |
| Full document contents (OCR, Document Intelligence) | Often contains sensitive business or personal data |

**What to log instead:** Request metadata (timestamp, endpoint, status code, latency, document count, token count). Enough to debug and monitor without storing sensitive content.

> **Exam note:** The exam may ask what to configure to avoid logging PII. The answer is: use diagnostic settings with `RequestResponse` logs but implement application-level filtering to strip sensitive fields before they reach your own logging pipeline. Azure's built-in diagnostic logs redact keys but not user content.

---

## Costs

<!-- Budget/limits strategy — Thursday -->

### Budget Strategy

| Control | Configuration |
|---|---|
| Azure Budget | Set on `ai102-rsg-eus` resource group; alert at 80% and 100% of monthly cap |
| AI Services tier | S0 — pay-per-call; no upfront commitment |
| Storage | LRS — cheapest redundancy; Hot tier for active use |
| Log Analytics | 30-day retention (free tier); ingestion charges apply but minimal for lab traffic |
| Teardown | Destroy all resources via Terraform when not actively studying |

### Cost Controls

- **Tag filtering:** All resources tagged `project: ai102` — filter cost analysis by tag to isolate lab spend
- **Terraform destroy:** Run `terraform destroy` at the end of each study session to avoid idle charges
- **S0 limits:** Multi-service S0 has per-minute call rate limits (varies by API); stay well under for lab use
- **No autoscale:** Lab doesn't need it; avoid accidentally provisioning higher tiers

### Estimated Monthly Cost (Active Lab)

| Resource | Estimate |
|---|---|
| AI Services (S0) | ~$0–5 (pay-per-call, low volume) |
| Key Vault | ~$0 (minimal operations) |
| Storage (LRS Hot) | ~$1–2 (small dataset) |
| Log Analytics | ~$0 (under free ingestion cap) |
| **Total** | **< $10/month with teardown discipline** |

## Networking / Private Endpoints

<!-- VNet integration, private endpoints, DNS resolution, service endpoints -->

## Responsible AI Notes

<!-- Guardrails, data sensitivity, misuse handling — Friday -->

### Microsoft's Responsible AI Principles

The exam expects familiarity with all six. These apply to every Azure AI service.

| Principle | What it means in practice |
|---|---|
| **Fairness** | Test for bias across demographics; monitor model outputs for disparate impact |
| **Reliability & Safety** | Handle errors gracefully; set confidence thresholds; fall back to human review when uncertain |
| **Privacy & Security** | Minimize data collection; encrypt at rest and in transit; control access via RBAC and Key Vault |
| **Inclusiveness** | Design for accessibility; support multiple languages and input modalities where possible |
| **Transparency** | Document what the model can and can't do; disclose AI-generated content to end users |
| **Accountability** | Assign human oversight; maintain audit logs; establish review processes for high-stakes decisions |

### Content Filtering

Azure AI Services (especially OpenAI and Content Safety) include built-in content filters.

| Filter category | Default behavior |
|---|---|
| Hate | Blocked at medium and high severity |
| Sexual | Blocked at medium and high severity |
| Violence | Blocked at medium and high severity |
| Self-harm | Blocked at medium and high severity |

- Filters are **on by default** for Azure OpenAI — cannot be fully disabled without Microsoft approval
- Custom severity thresholds can be configured per category
- Content filtering results are available in API response headers for logging

> **Exam note:** If a question asks how to prevent harmful outputs from an Azure OpenAI deployment, the answer is content filtering configuration — not prompt engineering alone.

### Data Sensitivity Handling

| Data type | Guardrail |
|---|---|
| PII in user input | Strip or mask before sending to AI services when possible; use AI Services PII detection endpoint to identify and redact |
| Documents with sensitive content | Process in-region; don't store raw outputs longer than needed; use customer-managed keys (CMK) for encryption if required |
| API keys and tokens | Key Vault only; never log, never commit to source control |
| Model outputs | Don't treat as ground truth; validate before acting on high-stakes results |

### Misuse Prevention

| Risk | Mitigation |
|---|---|
| Prompt injection | Validate and sanitize user inputs; use system messages to constrain behavior; monitor for unusual patterns |
| Excessive usage / abuse | Rate limiting via API Management or application-level throttling; monitor for anomalous call volumes |
| Unauthorized access | Entra ID + managed identity for production; RBAC scoped to least privilege; network restrictions (private endpoints) |
| Data exfiltration via model | Limit response length; avoid returning raw retrieved documents; filter outputs |

### Transparency Requirements

- **Disclose AI use:** End users should know when they're interacting with AI-generated content
- **Document limitations:** Every deployment should state what the model is good at and where it fails
- **Provide recourse:** Users should have a path to human review when AI output affects them

### Human Oversight

- No AI output should trigger irreversible actions without human confirmation in high-stakes scenarios
- Confidence thresholds: route low-confidence results to human review queues
- Regular audits: review model performance, fairness metrics, and content filter logs periodically

> **Exam note:** The exam frames Responsible AI as a "plan and manage" concern — expect questions about which principle applies to a scenario, and what Azure feature addresses it (e.g., Content Safety API for harmful content, PII detection for privacy, RBAC for accountability).
