"""Cosmos DB persistence for classified job results.

Provides upsert, query, and dedup operations against the
'jobscorer.results' container using DefaultAzureCredential (RBAC).
"""

import hashlib
import logging
from datetime import datetime, timezone

from azure.cosmos import CosmosClient

logger = logging.getLogger(__name__)


def _build_doc_id(title: str, company: str, url: str) -> str:
    """Build a deterministic document ID from job listing fields.

    Uses SHA-256 hash of title+company+url, truncated to 16 hex chars.
    """
    payload = f"{title}|{company}|{url}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _get_container(endpoint: str, credential, db_name: str, container_name: str):
    """Get a Cosmos DB container client."""
    client = CosmosClient(url=endpoint, credential=credential)
    database = client.get_database_client(db_name)
    return database.get_container_client(container_name)


def upsert_job_result(
    endpoint: str,
    credential,
    db: str,
    container: str,
    listing: dict,
    classification: dict,
    gap: dict,
    search_query: str,
    run_date: str,
) -> dict:
    """Upsert a classified job result into Cosmos DB.

    Args:
        endpoint: Cosmos DB account endpoint.
        credential: Azure credential (DefaultAzureCredential or key).
        db: Database name.
        container: Container name.
        listing: Job listing dict with title, company, location, url, etc.
        classification: ClassificationResult dict.
        gap: GapAnalysisResult dict.
        search_query: The search query that found this job.
        run_date: Date of the search run (YYYY-MM-DD).

    Returns:
        The upserted document.
    """
    container_client = _get_container(endpoint, credential, db, container)

    doc_id = _build_doc_id(
        listing.get("title", ""),
        listing.get("company", ""),
        listing.get("url", ""),
    )

    document = {
        "id": doc_id,
        "company": listing.get("company", "Unknown"),
        "title": listing.get("title", ""),
        "location": listing.get("location", ""),
        "url": listing.get("url", ""),
        "date_posted": listing.get("date_posted", ""),
        "employment_type": listing.get("employment_type", ""),
        "source": listing.get("source", ""),
        # Classification fields
        "category_id": classification.get("category_id"),
        "category_name": classification.get("category_name", ""),
        "confidence": classification.get("confidence", ""),
        "reasoning": classification.get("reasoning", ""),
        "skills_match_pct": classification.get("skills_match_pct", 0),
        "suggested_action": classification.get("suggested_action", ""),
        # Gap analysis fields
        "matched_skills_count": len(gap.get("matched_skills", [])),
        "missing_skills_count": len(gap.get("missing_skills", [])),
        "gap_summary": gap.get("summary", ""),
        "gap_recommendations": gap.get("recommendations", []),
        # Run metadata
        "search_query": search_query,
        "run_date": run_date,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    result = container_client.upsert_item(document)
    logger.info("Upserted result: %s — %s at %s", doc_id, document["title"], document["company"])
    return result


def query_results(
    endpoint: str,
    credential,
    db: str,
    container: str,
    date_from: str | None = None,
    date_to: str | None = None,
    company: str | None = None,
    category: int | None = None,
) -> list[dict]:
    """Query stored job results with optional filters.

    Args:
        endpoint: Cosmos DB account endpoint.
        credential: Azure credential.
        db: Database name.
        container: Container name.
        date_from: Filter results on or after this date (YYYY-MM-DD).
        date_to: Filter results on or before this date (YYYY-MM-DD).
        company: Filter by company name (partition key).
        category: Filter by category_id.

    Returns:
        List of result documents.
    """
    container_client = _get_container(endpoint, credential, db, container)

    conditions = ["1=1"]
    parameters = []

    if date_from:
        conditions.append("c.run_date >= @date_from")
        parameters.append({"name": "@date_from", "value": date_from})

    if date_to:
        conditions.append("c.run_date <= @date_to")
        parameters.append({"name": "@date_to", "value": date_to})

    if company:
        conditions.append("c.company = @company")
        parameters.append({"name": "@company", "value": company})

    if category is not None:
        conditions.append("c.category_id = @category")
        parameters.append({"name": "@category", "value": category})

    query = f"SELECT * FROM c WHERE {' AND '.join(conditions)} ORDER BY c.run_date DESC"

    items = list(container_client.query_items(
        query=query,
        parameters=parameters if parameters else None,
        enable_cross_partition_query=company is None,
    ))

    logger.info("Query returned %d results", len(items))
    return items


def result_exists(
    endpoint: str,
    credential,
    db: str,
    container: str,
    doc_id: str,
    company: str,
) -> bool:
    """Check if a result document already exists (for dedup).

    Args:
        endpoint: Cosmos DB account endpoint.
        credential: Azure credential.
        db: Database name.
        container: Container name.
        doc_id: Document ID to check.
        company: Partition key value.

    Returns:
        True if the document exists.
    """
    container_client = _get_container(endpoint, credential, db, container)

    try:
        container_client.read_item(item=doc_id, partition_key=company)
        return True
    except Exception:
        return False
