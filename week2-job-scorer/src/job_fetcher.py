"""Job Fetcher — Discover job listings from the web via JSearch API (RapidAPI).

Fetches job listings for a specific company with full filter support.
Results feed directly into the existing classification pipeline.

Usage:
    from src.job_fetcher import fetch_jobs, JobSearchFilters

    filters = JobSearchFilters(company="Microsoft", keywords="data engineer")
    listings = fetch_jobs(filters, api_key="your-rapidapi-key")
    for listing in listings:
        result = classify(resume_text, listing.description, ...)
"""

import logging
import os
from typing import Literal

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_HOST = "jsearch.p.rapidapi.com"


class JobFetchError(Exception):
    """Raised when job fetching fails due to API or network errors."""


class JobSearchFilters(BaseModel):
    """Filter criteria for job search."""

    company: str
    keywords: str | None = None
    location: str | None = None
    date_posted: Literal["all", "today", "3days", "week", "month"] = "week"
    employment_type: Literal["fulltime", "parttime", "contractor", "intern"] | None = None
    max_results: int = Field(default=10, ge=1, le=50)


class JobListing(BaseModel):
    """A single fetched job listing."""

    title: str
    company: str
    location: str
    description: str
    url: str
    date_posted: str
    employment_type: str
    source: str


def _build_jsearch_query(filters: JobSearchFilters) -> dict:
    """Map JobSearchFilters to JSearch API query parameters."""
    query_parts = [filters.company]
    if filters.keywords:
        query_parts.append(filters.keywords)

    params = {
        "query": " ".join(query_parts),
        "num_pages": "1",
        "page": "1",
        "date_posted": filters.date_posted,
    }

    if filters.location:
        params["query"] += f" in {filters.location}"

    if filters.employment_type:
        type_map = {
            "fulltime": "FULLTIME",
            "parttime": "PARTTIME",
            "contractor": "CONTRACTOR",
            "intern": "INTERN",
        }
        params["employment_types"] = type_map.get(filters.employment_type, filters.employment_type.upper())

    params["num_pages"] = "1"

    return params


def _resolve_api_key(api_key: str | None) -> str:
    """Resolve API key from explicit param, env var, or Key Vault."""
    if api_key:
        return api_key

    env_key = os.environ.get("RAPIDAPI_KEY")
    if env_key:
        return env_key

    # Try Key Vault as last resort
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = os.environ.get("AZURE_KEY_VAULT_URI", "https://ai102-kvt2-eus.vault.azure.net/")
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        secret = client.get_secret("rapidapi-key")
        if secret.value:
            return secret.value
    except Exception as e:
        logger.debug("Could not retrieve rapidapi-key from Key Vault: %s", e)

    raise JobFetchError(
        "No RapidAPI key found. Provide via api_key parameter, "
        "RAPIDAPI_KEY env var, or 'rapidapi-key' Key Vault secret."
    )


def _parse_jsearch_response(data: dict) -> list[JobListing]:
    """Parse JSearch API response JSON into JobListing objects."""
    listings = []
    for job in data.get("data", []):
        description = (job.get("job_description") or "").strip()
        if not description:
            logger.warning("Skipping listing '%s' — empty description", job.get("job_title", "unknown"))
            continue

        listings.append(JobListing(
            title=job.get("job_title", "Unknown Title"),
            company=job.get("employer_name", "Unknown Company"),
            location=_format_location(job),
            description=description,
            url=job.get("job_apply_link") or job.get("job_google_link", ""),
            date_posted=job.get("job_posted_at_datetime_utc", ""),
            employment_type=job.get("job_employment_type", "unknown"),
            source=job.get("job_publisher", "JSearch"),
        ))

    return listings


def _format_location(job: dict) -> str:
    """Format location from JSearch job data."""
    city = job.get("job_city", "")
    state = job.get("job_state", "")
    country = job.get("job_country", "")
    is_remote = job.get("job_is_remote", False)

    parts = [p for p in [city, state, country] if p]
    location = ", ".join(parts) or "Unknown"

    if is_remote:
        location = f"Remote — {location}" if parts else "Remote"

    return location


def _fetch_jsearch(filters: JobSearchFilters, api_key: str) -> list[JobListing]:
    """Call JSearch API and return parsed JobListing objects."""
    params = _build_jsearch_query(filters)
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }

    try:
        response = requests.get(
            JSEARCH_BASE_URL,
            headers=headers,
            params=params,
            timeout=30,
        )
    except requests.ConnectionError as e:
        raise JobFetchError(f"Network error connecting to JSearch API: {e}") from e
    except requests.Timeout as e:
        raise JobFetchError(f"JSearch API request timed out: {e}") from e

    if response.status_code == 429:
        raise JobFetchError("JSearch API rate limit exceeded. Please wait and try again.")
    if response.status_code >= 400:
        raise JobFetchError(
            f"JSearch API error {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    listings = _parse_jsearch_response(data)

    # Trim to max_results
    listings = listings[: filters.max_results]

    if not listings:
        logger.warning("No job listings found for query: %s", params.get("query"))

    return listings


def fetch_jobs(filters: JobSearchFilters, api_key: str | None = None) -> list[JobListing]:
    """Fetch job listings from the web using JSearch API.

    Args:
        filters: Search criteria.
        api_key: RapidAPI key. Falls back to RAPIDAPI_KEY env var or Key Vault.

    Returns:
        List of JobListing objects.

    Raises:
        JobFetchError: On API/network errors or missing API key.
    """
    resolved_key = _resolve_api_key(api_key)
    return _fetch_jsearch(filters, resolved_key)
