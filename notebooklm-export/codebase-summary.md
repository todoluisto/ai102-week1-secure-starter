# AI-102 SANDBOX — Full Codebase Summary

## Project Overview

This is a study companion repository for the Microsoft AI-102 (Azure AI Engineer Associate) certification exam. The centerpiece project is a **Job Opportunity Scorer** — an AI-powered system that classifies job descriptions against a candidate's resume into 5 actionable categories using Azure Document Intelligence and Azure OpenAI.

The repo is structured by weekly exam topics, with each week having its own infrastructure-as-code (Terraform) and application code.

## Repository Structure

```
AI102-SANDBOX/
├── README.md                          # Course overview and weekly progress tracker
├── week1-provision-secure/            # Azure AI provisioning and security foundations
│   ├── README.md                      # Architecture guide (multi-service, Key Vault, RBAC)
│   └── infra/                         # Terraform: Resource Group, Cognitive Account, Key Vault, Storage, Log Analytics
│
├── week2-job-scorer/                  # PRIMARY PROJECT: AI-powered job classifier
│   ├── README.md                      # Complete setup guide, architecture, cost analysis
│   ├── architecture.md                # Mermaid diagrams (data flow, auth paths)
│   ├── app.py                         # Streamlit web UI
│   ├── requirements.txt               # Python dependencies
│   ├── src/                           # Core application modules
│   │   ├── scorer.py                  # CLI orchestrator
│   │   ├── job_analyzer.py            # Azure OpenAI classification engine
│   │   ├── resume_parser.py           # Document Intelligence + OpenAI resume processing
│   │   ├── job_scraper.py             # Web scraping + job extraction
│   │   ├── job_fetcher.py             # JSearch API integration (RapidAPI)
│   │   └── categories.py             # 5-category classification schema
│   ├── prompts/
│   │   └── classify.txt               # Jinja2 prompt template for classification
│   ├── data/
│   │   ├── sample_jobs/               # 50 labeled test job descriptions
│   │   └── evaluation/                # Metrics results and cached resume profiles
│   ├── tests/                         # Pytest evaluation framework
│   │   ├── test_scorer.py             # Accuracy, F1, confusion matrix, calibration
│   │   └── test_job_fetcher.py        # API integration tests
│   └── infra/                         # Terraform for Week 2 Azure resources
│
├── week2-text-speech/                 # Placeholder for Text Analytics & Speech Services
└── (week3-5 planned but not yet started)
```

## Architecture — Job Opportunity Scorer

### High-Level Data Flow

The system has three main pipelines:

**Pipeline 1: Resume Processing**
1. User uploads a PDF resume
2. Azure Document Intelligence (prebuilt-layout model) extracts raw text from the PDF
3. Azure OpenAI (GPT-4o-mini) structures the raw text into a typed ResumeProfile (skills, experience years, seniority, tech stack, education, summary)
4. The structured profile is cached to disk to avoid re-processing

**Pipeline 2: Job Classification**
1. A job description (text) is paired with the structured resume profile
2. A Jinja2 prompt template (classify.txt) is rendered with: category definitions, resume profile, and job description
3. Azure OpenAI classifies the job into one of 5 categories using structured outputs (Pydantic schema validation)
4. The result includes: category ID/name, confidence level, reasoning, skills match percentage, and a suggested action

**Pipeline 3: Job Discovery (Optional)**
1. User provides search filters (company, keywords, location, date range, employment type)
2. The JSearch API (via RapidAPI) returns matching job listings
3. Each listing is fed through Pipeline 2 for classification

### Azure Resources Deployed

| Resource | Name | Type | SKU | Region | Purpose |
|----------|------|------|-----|--------|---------|
| Resource Group | ai102-rsg-eus | — | — | East US | Container |
| Azure OpenAI (primary) | ai102-oai-eus | OpenAI | S0 | East US | Classification engine (GPT-4o-mini) |
| Azure OpenAI (fallback) | ai102-oai-ncus | OpenAI | S0 | North Central US | Multi-region resilience |
| Document Intelligence | ai102-fri-eus | FormRecognizer | S0 | East US | PDF text extraction |
| Key Vault | ai102-kvt2-eus | Key Vault | Standard | East US | Secret management |
| Log Analytics | ai102-law2-eus | Log Analytics | PerGB2018 | East US | Diagnostic logging |

### Authentication Patterns

Two authentication paths are implemented side by side:

**Path 1 — API Key (via Key Vault):**
`DefaultAzureCredential` → Key Vault (RBAC: Key Vault Secrets Officer) → Retrieve API keys → Pass keys to OpenAI/Document Intelligence SDKs

**Path 2 — Managed Identity (no secrets):**
`DefaultAzureCredential` → Token provider → Pass Entra ID token directly to SDKs (requires Cognitive Services User RBAC on each resource)

### Multi-Region Failover

The classifier tries the primary endpoint (East US) first. If it fails (HTTP 429 rate limit, 503 outage, or any error), it automatically retries on the fallback endpoint (North Central US). This demonstrates resilience patterns for the exam's "plan and manage" objective.

### Structured Outputs

The classification engine uses two strategies:
1. **Primary**: `client.beta.chat.completions.parse()` with a Pydantic model (`ClassificationResult`) for type-safe, schema-validated responses
2. **Fallback**: `response_format: {"type": "json_object"}` + manual Pydantic validation if the API version doesn't support structured outputs

## Classification Categories

The 5-bucket system with clear criteria:

| # | Category | When to Use | Skills Match | Action |
|---|----------|-------------|-------------|--------|
| 1 | Strong Fit — Apply Now | 80%+ match, right seniority, high tech overlap | ≥80% | Draft tailored application this week |
| 2 | Stretch Role — Worth a Shot | 60-79% match, growth opportunity, appealing company | 60-79% | Apply with narrative bridging the gap |
| 3 | Interesting — Not Now | Great company, wrong timing/location/seniority | Varies | Save to watchlist, revisit in 30 days |
| 4 | Needs More Research | Vague JD, unclear scope, unfamiliar company | Unknown | Research company before committing time |
| 5 | Not Relevant | Wrong stack, spam, off target, 2+ level mismatch | <40% | Archive immediately |

## Module Deep Dive

### scorer.py — CLI Orchestrator
- Entry point for the command-line interface
- Modes: single job (`--job`), batch directory (`--jobs`), web search (`--search-company`)
- Wires together: Key Vault secrets retrieval → resume parsing (with caching) → job classification → formatted output
- Outputs: console table with category/confidence/match + category distribution summary + optional JSON export

### job_analyzer.py — Classification Engine
- Core classification logic using Azure OpenAI
- Uses Jinja2 template rendering to construct prompts with category definitions injected
- Pydantic `ClassificationResult` model: category_id (1-5), category_name, confidence (high/medium/low), reasoning, skills_match_pct (0-100), suggested_action
- Multi-region try/except failover between East US and North Central US
- Both structured outputs and JSON mode fallback paths

### resume_parser.py — Resume Processing Pipeline
- Step 1: Azure Document Intelligence `prebuilt-layout` model extracts text from PDF (supports both API key and managed identity auth)
- Step 2: Azure OpenAI structures raw text into a `ResumeProfile` dataclass with fields: skills, experience_years, seniority, tech_stack, education, summary
- Caching: saves parsed profiles as JSON to avoid expensive re-processing
- The `ResumeProfile.to_prompt_text()` method formats the profile for injection into classification prompts

### job_scraper.py — Web Job Extraction
- Fetches job posting URLs with httpx
- Cleans HTML with BeautifulSoup (removes scripts, styles, nav, footer)
- Uses Azure OpenAI structured outputs to extract: title, salary, company, description
- Truncates page text to 12K characters for token budget
- Same multi-region failover as the classifier

### job_fetcher.py — Job Discovery via JSearch
- Integrates with RapidAPI's JSearch (job board aggregator)
- Filters: company name, keywords, location, date posted, employment type, max results
- API key resolution chain: parameter → environment variable → Key Vault
- Returns typed `JobListing` objects (title, company, location, description, URL, date, type)

### categories.py — Classification Schema
- Defines 5 categories as dataclasses with: id, name, criteria (list of strings), suggested_action
- `format_categories_for_prompt()` converts categories to text for Jinja2 template injection

### app.py — Streamlit Web UI
- Sidebar: Azure configuration, resume upload, profile display
- Three tabs: URL fetch, paste text, job search
- Session state management: profile, secrets, classification history
- Features: resume caching, URL extraction with validation, batch job search classification, JSON export

## Prompt Engineering

The classification prompt (prompts/classify.txt) is a Jinja2 template with:
- System section: role definition, category definitions (injected), evaluation dimensions (skills match, seniority alignment, tech stack overlap, domain relevance, location compatibility), output format schema
- User section (after `---` separator): candidate profile and job description
- Temperature: 0.2 for consistent, deterministic classifications

## Evaluation Framework

- 50 labeled sample job descriptions across all 5 categories (10 Strong Fit, 10 Stretch, 10 Interesting, 8 Needs Research, 12 Not Relevant)
- Metrics: overall accuracy, per-category precision/recall/F1, 5×5 confusion matrix, confidence calibration
- Can run as pytest tests (unit tests need no Azure; full eval needs deployed resources)
- Results saved to `data/evaluation/results.json`

## Infrastructure as Code (Terraform)

Both week1 and week2 have dedicated Terraform configurations:
- Provider: `hashicorp/azurerm` v4.62.1+
- Resources are tagged and named with consistent prefixes (`ai102-`)
- Key Vault uses RBAC access policies
- Diagnostic settings route Audit, RequestResponse, and Trace logs to Log Analytics
- State managed locally in `terraform.tfstate`

## Dependencies (Python)

| Package | Version | Purpose |
|---------|---------|---------|
| azure-ai-documentintelligence | ≥1.0.0 | PDF text extraction |
| azure-identity | ≥1.15.0 | DefaultAzureCredential, token providers |
| azure-keyvault-secrets | ≥4.8.0 | Secret retrieval from Key Vault |
| openai | ≥1.42.0 | Azure OpenAI chat completions, structured outputs |
| jinja2 | ≥3.1.0 | Prompt template rendering |
| pydantic | ≥2.8.0 | Data validation, structured output schemas |
| scikit-learn | ≥1.4.0 | Evaluation metrics (precision, recall, F1, confusion matrix) |
| httpx | ≥0.27.0 | Async HTTP client for web scraping |
| beautifulsoup4 | ≥4.12.0 | HTML parsing and cleaning |
| requests | ≥2.31.0 | HTTP requests for JSearch API |
| streamlit | ≥1.32.0 | Web UI framework |
| tabulate | ≥0.9.0 | CLI table formatting |
| pytest | ≥8.0.0 | Test framework |

## AI-102 Exam Mapping

| Exam Objective | Implementation |
|---|---|
| Plan and manage an Azure AI solution | Terraform IaC, Key Vault RBAC, multi-region deployment, diagnostic settings, cost management |
| Implement document intelligence solutions | Document Intelligence prebuilt-layout for PDF resume parsing |
| Implement generative AI solutions | Azure OpenAI chat.completions with structured outputs, Jinja2 prompt engineering |
| Secure Azure AI services | DefaultAzureCredential + API key dual paths, Key Vault secret management, RBAC roles |
| Monitor Azure AI services | Diagnostic settings (Audit, RequestResponse, Trace) → Log Analytics workspace |

## Cost Profile

Monthly estimate for lab use: < $2/month total
- Azure OpenAI GPT-4o-mini: < $1 (~50 API calls)
- Document Intelligence: < $0.10 (1-2 resume parses)
- Key Vault: < $0.01
- Log Analytics: < $0.50
- Teardown: `terraform destroy` when not in use
