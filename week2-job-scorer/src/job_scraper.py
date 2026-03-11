"""Job posting scraper using HTTP fetch + Azure OpenAI extraction.

Fetches a job posting URL, strips HTML to clean text, then uses
Azure OpenAI structured outputs to extract title, salary, company,
and the full job description.
"""

import json
import logging

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from .job_analyzer import _build_client

logger = logging.getLogger(__name__)

MAX_PAGE_CHARS = 12_000

EXTRACTION_PROMPT = """\
You are a job posting extractor. Given raw text scraped from a job posting webpage, extract:
- job_title: The exact job title
- salary: Salary or compensation range if mentioned, otherwise null
- company: The hiring company name if mentioned, otherwise null
- job_description: The full job description text (responsibilities, requirements, qualifications). \
Preserve all detail. Do not summarize.

Respond with valid JSON matching this schema:
{
  "job_title": "Senior Data Engineer",
  "salary": "$150,000 - $180,000",
  "company": "Acme Corp",
  "job_description": "We are looking for..."
}
"""


class JobPosting(BaseModel):
    """Structured output schema for extracted job posting."""

    job_title: str
    salary: str | None = None
    company: str | None = None
    job_description: str


def fetch_page(url: str) -> str:
    """Fetch a URL and return cleaned text content.

    Strips scripts, styles, nav, footer, and header tags, then extracts
    visible text. Truncates to MAX_PAGE_CHARS to stay within token budgets.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        raise ValueError(f"Expected HTML but got content-type: {content_type}")

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    if len(text) > MAX_PAGE_CHARS:
        logger.warning("Page text truncated from %d to %d chars", len(text), MAX_PAGE_CHARS)
        text = text[:MAX_PAGE_CHARS]

    logger.info("Fetched %d chars from %s", len(text), url)
    return text


def extract_job_posting(
    page_text: str,
    endpoint: str,
    key: str | None = None,
    deployment_name: str = "gpt-4o-mini",
    use_identity: bool = False,
) -> JobPosting:
    """Use Azure OpenAI to extract structured job posting fields from page text."""
    client = _build_client(endpoint, key, use_identity)

    try:
        response = client.beta.chat.completions.parse(
            model=deployment_name,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": page_text},
            ],
            response_format=JobPosting,
            temperature=0.1,
        )
        result = response.choices[0].message.parsed
        logger.info(
            "Extraction (structured) — tokens: %d input, %d output",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return result
    except Exception as e:
        logger.warning("Structured outputs failed (%s), falling back to json_object mode", e)

        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": page_text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = json.loads(response.choices[0].message.content)
        logger.info(
            "Extraction (json_object) — tokens: %d input, %d output",
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return JobPosting(**raw)


def scrape_job(
    url: str,
    primary_endpoint: str,
    primary_key: str | None = None,
    primary_deployment: str = "gpt-4o-mini",
    fallback_endpoint: str | None = None,
    fallback_key: str | None = None,
    fallback_deployment: str = "gpt-4o-mini",
    use_identity: bool = False,
) -> JobPosting:
    """Fetch a job posting URL and extract structured fields.

    Tries the primary Azure OpenAI endpoint first. Falls back to
    the secondary endpoint if the primary fails.
    """
    page_text = fetch_page(url)

    try:
        return extract_job_posting(
            page_text, primary_endpoint, primary_key, primary_deployment, use_identity
        )
    except Exception as e:
        logger.warning("Primary endpoint failed for extraction: %s", e)
        if not fallback_endpoint:
            raise

    logger.info("Retrying extraction with fallback endpoint")
    return extract_job_posting(
        page_text, fallback_endpoint, fallback_key, fallback_deployment, use_identity
    )
