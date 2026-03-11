# Architecture Diagram

```mermaid
graph TD
    subgraph Client
        CLI["scorer.py<br/>CLI"]
        UI["app.py<br/>Streamlit"]
    end

    subgraph RG["ai102-rsg-eus · Resource Group"]
        KV["ai102-kvt2-eus<br/>Key Vault · Standard"]
        OAI["ai102-oai-eus<br/>Azure OpenAI · S0<br/>GPT-4o-mini · East US"]
        OAI_FB["ai102-oai-ncus<br/>Azure OpenAI · S0<br/>GPT-4o-mini · North Central US"]
        FRI["ai102-fri-eus<br/>Document Intelligence · S0<br/>prebuilt-layout · East US"]
        LAW["ai102-law2-eus<br/>Log Analytics<br/>PerGB2018 · East US"]
    end

    %% Auth Path 1: API Key flow via Key Vault
    CLI -. "1a DefaultAzureCredential" .-> KV
    UI -. "1a DefaultAzureCredential" .-> KV
    KV -. "1b Retrieve API keys" .-> OAI
    KV -. "1b Retrieve API keys" .-> FRI

    %% Auth Path 2: Entra ID direct token
    CLI == "2 Entra ID token<br/>--auth identity" ==> OAI
    CLI == "2 Entra ID token" ==> FRI

    %% SDK and REST data flows
    CLI -- "REST: Parse resume PDF" --> FRI
    CLI -- "SDK: Classify JD" --> OAI
    UI -- "SDK: Classify JD" --> OAI

    %% Multi-region fallback
    OAI -- "fallback on 429/503" --> OAI_FB

    %% Diagnostic log flow
    OAI -. "diag: Audit, Request,<br/>Response, Trace" .-> LAW
    OAI_FB -. "diag logs" .-> LAW
    FRI -. "diag logs" .-> LAW
```

## Legend

| Line Style | Meaning |
|---|---|
| `-- solid thin --` | SDK / REST data calls (current build) |
| `== solid thick ==` | Entra ID auth path (identity mode) |
| `-. dashed .-` | Key Vault secret retrieval and diagnostic log flow |
