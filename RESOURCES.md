## Azure Resource Plan

### Resources

| Resource | Name | Kind / SKU | Region | Purpose |
|----------|------|------------|--------|---------|
| Resource Group | `ai102-rsg-eus` | — | East US | Contains all lab resources |
| AI Services (multi-service) | `ai102-cog-eus` | `CognitiveServices` / S0 | East US | Language, Vision, Speech, Decision via single endpoint |
| Key Vault | `ai102-kvt-eus` | Standard (RBAC access model) | East US | API keys and secrets |
| Storage Account | `ai102stgeus` | StorageV2 / Standard LRS / Hot | East US | Image and document storage (Weeks 3–4) |
| Log Analytics Workspace | `ai102-law-eus` | Pay-as-you-go (30-day retention) | East US | Diagnostic logs for AI Services |

### Naming Convention

```
ai102-<svc>-<region>
```

- `<svc>` — 3-letter service abbreviation: `rsg`, `cog`, `kvt`, `stg`, `law`
- `<region>` — shorthand: `eus` (East US), `wus` (West US), `neu` (North Europe), etc.
- Storage accounts are the exception — no hyphens allowed, 3–24 lowercase alphanumeric only

### Region

**East US** — all required AI Services features are available, no premium pricing, and reasonable latency for US-based dev.

### Endpoint

Using **custom subdomain** (`ai102-cog-eus.cognitiveservices.azure.com`) from the start. Required for Entra ID auth and private endpoints — can't be added after resource creation.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Multi-service vs single-service | Multi-service | One key pair, one endpoint, simpler management. Use single-service only when you need per-service RBAC or network isolation. |
| Auth | API key for dev, Entra ID + managed identity for production | Keys in Key Vault, never in code. Managed identity eliminates secret management entirely. |
| Redundancy | LRS | Lab environment — cost control over durability. |

### Tags

All resources tagged with `project: ai102` for cost filtering and organization.

### Deferred Resources

- **Azure AI Search** — Week 4
- **Azure OpenAI** (if separate resource needed) — Week 5
- **Private endpoints / VNet** — Week 4+
