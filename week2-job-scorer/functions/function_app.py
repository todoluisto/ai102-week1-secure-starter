"""Azure Functions app — HTTP triggers (API) + Timer trigger (scheduled search).

v2 Python programming model. All triggers defined in this single file.

Imports the existing src/ modules for classification, gap analysis,
job fetching, and resume parsing.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient

# Add project root to path so we can import src/ modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cosmos_store import (
    _build_doc_id,
    query_results,
    result_exists,
    upsert_job_result,
)
from src.gap_analyzer import GapAnalysisResult, analyze_gap
from src.job_analyzer import ClassificationResult, classify
from src.job_fetcher import JobSearchFilters, fetch_jobs
from src.resume_parser import ResumeProfile
from src.scorer import _get_secrets, score_job_with_gap

logger = logging.getLogger(__name__)

app = func.FunctionApp()

# ─── Module-level caches ──────────────────────────────────────────
_cached_secrets: dict | None = None
_cached_credential: DefaultAzureCredential | None = None


def _get_credential() -> DefaultAzureCredential:
    """Get or create a cached DefaultAzureCredential."""
    global _cached_credential
    if _cached_credential is None:
        _cached_credential = DefaultAzureCredential()
    return _cached_credential


def _get_cached_secrets() -> dict[str, str]:
    """Retrieve and cache secrets from Key Vault."""
    global _cached_secrets
    if _cached_secrets is None:
        vault_url = os.environ.get(
            "AZURE_KEY_VAULT_URI", "https://ai102-kvt2-eus.vault.azure.net/"
        )
        _cached_secrets = _get_secrets(vault_url)
    return _cached_secrets


def _get_cosmos_config() -> tuple[str, DefaultAzureCredential, str, str]:
    """Return Cosmos DB connection config from environment."""
    endpoint = os.environ["COSMOS_ENDPOINT"]
    credential = _get_credential()
    db = os.environ.get("COSMOS_DATABASE", "jobscorer")
    container = os.environ.get("COSMOS_CONTAINER", "results")
    return endpoint, credential, db, container


def _read_blob_json(blob_name: str) -> dict:
    """Read a JSON blob from the function-config container."""
    account_name = os.environ["CONFIG_STORAGE_ACCOUNT_NAME"]
    container_name = os.environ.get("CONFIG_CONTAINER_NAME", "function-config")
    credential = _get_credential()

    blob_url = f"https://{account_name}.blob.core.windows.net"
    blob_service = BlobServiceClient(account_url=blob_url, credential=credential)
    blob_client = blob_service.get_blob_client(container_name, blob_name)

    data = blob_client.download_blob().readall()
    return json.loads(data)


def _load_resume_profile() -> ResumeProfile:
    """Load resume profile from Blob Storage."""
    profile_data = _read_blob_json("resume_profile.json")
    return ResumeProfile(**profile_data)


# ─── Timer Trigger: Scheduled Job Search ──────────────────────────
@app.timer_trigger(
    schedule="0 0 14 * * 1-5",
    arg_name="timer",
    run_on_startup=False,
)
def scheduled_job_search(timer: func.TimerRequest) -> None:
    """Run scheduled job searches (weekdays at 2 PM UTC).

    Reads search config + resume profile from Blob Storage,
    fetches jobs, classifies new ones, and stores results in Cosmos DB.
    """
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("Scheduled job search starting — run_date=%s", run_date)

    if timer.past_due:
        logger.warning("Timer trigger is past due")

    try:
        config = _read_blob_json("search_config.json")
        profile = _load_resume_profile()
        secrets = _get_cached_secrets()
        cosmos_endpoint, cosmos_cred, cosmos_db, cosmos_container = _get_cosmos_config()
    except Exception as e:
        logger.error("Failed to load config/secrets: %s", e)
        return

    total_new = 0
    total_skipped = 0

    for search in config.get("searches", []):
        search_query = f"{search['company']} {search.get('keywords', '')}".strip()
        logger.info("Searching: %s", search_query)

        try:
            filters = JobSearchFilters(
                company=search["company"],
                keywords=search.get("keywords"),
                location=search.get("location"),
                max_results=search.get("max_results", 10),
            )
            rapidapi_key = secrets.get("rapidapi-key")
            listings = fetch_jobs(filters, api_key=rapidapi_key)
        except Exception as e:
            logger.error("Search failed for '%s': %s", search_query, e)
            continue

        for listing in listings:
            listing_dict = listing.model_dump()
            doc_id = _build_doc_id(listing.title, listing.company, listing.url)

            # Dedup — skip if already classified
            if result_exists(cosmos_endpoint, cosmos_cred, cosmos_db, cosmos_container, doc_id, listing.company):
                total_skipped += 1
                logger.debug("Skipping duplicate: %s", listing.title)
                continue

            try:
                classification, gap = score_job_with_gap(
                    resume_profile=profile,
                    job_description=listing.description,
                    secrets=secrets,
                )

                upsert_job_result(
                    endpoint=cosmos_endpoint,
                    credential=cosmos_cred,
                    db=cosmos_db,
                    container=cosmos_container,
                    listing=listing_dict,
                    classification=classification.model_dump(),
                    gap=gap.model_dump(),
                    search_query=search_query,
                    run_date=run_date,
                )
                total_new += 1
            except Exception as e:
                logger.error("Failed to classify '%s': %s", listing.title, e)

    logger.info(
        "Scheduled search complete — %d new results, %d skipped (duplicates)",
        total_new,
        total_skipped,
    )


# ─── HTTP Trigger: Classify Job ──────────────────────────────────
@app.route(route="jobs/classify", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def classify_job(req: func.HttpRequest) -> func.HttpResponse:
    """Classify a job description and return classification + gap analysis.

    Request body: { "job_description": "..." }
    Response: { "classification": {...}, "gap": {...} }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    job_description = body.get("job_description", "").strip()
    if not job_description:
        return func.HttpResponse(
            json.dumps({"error": "job_description is required"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        secrets = _get_cached_secrets()
        profile = _load_resume_profile()

        classification, gap = score_job_with_gap(
            resume_profile=profile,
            job_description=job_description,
            secrets=secrets,
        )

        return func.HttpResponse(
            json.dumps({
                "classification": classification.model_dump(),
                "gap": gap.model_dump(),
            }),
            mimetype="application/json",
        )
    except Exception as e:
        logger.error("Classification failed: %s", e)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


# ─── HTTP Trigger: Search Jobs ───────────────────────────────────
@app.route(route="jobs/search", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def search_jobs(req: func.HttpRequest) -> func.HttpResponse:
    """Search for jobs using JSearch API.

    Request body: JobSearchFilters JSON
    Response: list of JobListing dicts
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        filters = JobSearchFilters(**body)
        secrets = _get_cached_secrets()
        rapidapi_key = secrets.get("rapidapi-key")
        listings = fetch_jobs(filters, api_key=rapidapi_key)

        return func.HttpResponse(
            json.dumps([listing.model_dump() for listing in listings]),
            mimetype="application/json",
        )
    except Exception as e:
        logger.error("Search failed: %s", e)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


# ─── HTTP Trigger: Get Results ───────────────────────────────────
@app.route(route="results", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_results(req: func.HttpRequest) -> func.HttpResponse:
    """Query stored results from Cosmos DB.

    Query params: date_from, date_to, company, category
    Response: list of result documents
    """
    date_from = req.params.get("date_from")
    date_to = req.params.get("date_to")
    company = req.params.get("company")
    category_str = req.params.get("category")
    category = int(category_str) if category_str else None

    try:
        endpoint, credential, db, container = _get_cosmos_config()
        results = query_results(
            endpoint=endpoint,
            credential=credential,
            db=db,
            container=container,
            date_from=date_from,
            date_to=date_to,
            company=company,
            category=category,
        )

        return func.HttpResponse(
            json.dumps(results, default=str),
            mimetype="application/json",
        )
    except Exception as e:
        logger.error("Results query failed: %s", e)
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


# ─── HTTP Trigger: Health Check ──────────────────────────────────
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint.

    Response: { "status": "ok", "services": { ... } }
    """
    services = {}

    # Check Key Vault
    try:
        _get_cached_secrets()
        services["key_vault"] = "ok"
    except Exception as e:
        services["key_vault"] = f"error: {e}"

    # Check Cosmos DB
    try:
        endpoint, credential, db, container = _get_cosmos_config()
        query_results(endpoint, credential, db, container)
        services["cosmos_db"] = "ok"
    except Exception as e:
        services["cosmos_db"] = f"error: {e}"

    # Check Blob Storage
    try:
        _read_blob_json("search_config.json")
        services["blob_storage"] = "ok"
    except Exception as e:
        services["blob_storage"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"

    return func.HttpResponse(
        json.dumps({"status": overall, "services": services}),
        mimetype="application/json",
    )
