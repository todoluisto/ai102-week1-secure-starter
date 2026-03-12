"""Main orchestrator for the Job Opportunity Scorer.

Wires resume parsing and job classification together.
Supports both CLI batch mode and programmatic usage (for Streamlit).

Usage:
    # Single job description
    python -m src.scorer --resume data/my_resume.pdf --job "paste JD text here"

    # Batch mode (directory of .txt files)
    python -m src.scorer --resume data/my_resume.pdf --jobs data/sample_jobs/

    # With output file
    python -m src.scorer --resume data/my_resume.pdf --jobs data/sample_jobs/ --output data/evaluation/results.json

    # Using managed identity instead of API keys
    python -m src.scorer --resume data/my_resume.pdf --job "JD text" --auth identity
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from tabulate import tabulate

from .gap_analyzer import GapAnalysisResult, analyze_gap
from .job_analyzer import ClassificationResult, classify
from .job_fetcher import JobSearchFilters, fetch_jobs
from .resume_parser import ResumeProfile, parse_resume

logger = logging.getLogger(__name__)


def _get_secrets(vault_url: str) -> dict[str, str]:
    """Retrieve all required secrets from Key Vault using DefaultAzureCredential."""
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)

    secret_names = [
        "openai-key",
        "openai-endpoint",
        "openai-fallback-key",
        "openai-fallback-endpoint",
        "doc-intel-key",
        "doc-intel-endpoint",
        "rapidapi-key",
        "cosmos-endpoint",
    ]

    secrets = {}
    for name in secret_names:
        try:
            secrets[name] = client.get_secret(name).value
        except Exception as e:
            logger.warning("Could not retrieve secret '%s': %s", name, e)
            secrets[name] = None

    return secrets


def score_job(
    resume_profile: ResumeProfile,
    job_description: str,
    secrets: dict[str, str],
    deployment_name: str = "gpt-4o-mini",
    use_identity: bool = False,
) -> ClassificationResult:
    """Classify a single job description against a resume profile.

    Args:
        resume_profile: Parsed resume profile.
        job_description: Job description text.
        secrets: Dict of secrets from Key Vault.
        deployment_name: Model deployment name.
        use_identity: Use DefaultAzureCredential for AI services.

    Returns:
        ClassificationResult.
    """
    return classify(
        resume_profile_text=resume_profile.to_prompt_text(),
        job_description=job_description,
        primary_endpoint=secrets["openai-endpoint"],
        primary_key=secrets.get("openai-key"),
        primary_deployment=deployment_name,
        fallback_endpoint=secrets.get("openai-fallback-endpoint"),
        fallback_key=secrets.get("openai-fallback-key"),
        fallback_deployment=deployment_name,
        use_identity=use_identity,
    )


def score_job_with_gap(
    resume_profile: ResumeProfile,
    job_description: str,
    secrets: dict[str, str],
    deployment_name: str = "gpt-4o-mini",
    use_identity: bool = False,
) -> tuple[ClassificationResult, GapAnalysisResult]:
    """Classify a job and perform gap analysis.

    Returns:
        Tuple of (ClassificationResult, GapAnalysisResult).
    """
    classification = score_job(
        resume_profile, job_description, secrets, deployment_name, use_identity
    )

    gap = analyze_gap(
        resume_profile_text=resume_profile.to_prompt_text(),
        job_description=job_description,
        primary_endpoint=secrets["openai-endpoint"],
        primary_key=secrets.get("openai-key"),
        primary_deployment=deployment_name,
        fallback_endpoint=secrets.get("openai-fallback-endpoint"),
        fallback_key=secrets.get("openai-fallback-key"),
        fallback_deployment=deployment_name,
        use_identity=use_identity,
    )

    return classification, gap


def _load_job_files(jobs_dir: str) -> list[tuple[str, str]]:
    """Load job description text files from a directory.

    Returns:
        List of (filename, text) tuples.
    """
    jobs_path = Path(jobs_dir)
    files = sorted(jobs_path.glob("*.txt"))
    results = []
    for f in files:
        results.append((f.name, f.read_text().strip()))
    logger.info("Loaded %d job descriptions from %s", len(results), jobs_dir)
    return results


def _format_results_table(results: list[dict]) -> str:
    """Format classification results as a summary table."""
    table_data = []
    for r in results:
        table_data.append([
            r.get("filename", "—"),
            f"{r['category_id']}. {r['category_name']}",
            r["confidence"],
            f"{r['skills_match_pct']}%",
        ])

    return tabulate(
        table_data,
        headers=["Job", "Category", "Confidence", "Match"],
        tablefmt="simple",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Job Opportunity Scorer — classify jobs against your resume"
    )
    parser.add_argument(
        "--resume", required=True, help="Path to resume PDF file"
    )
    parser.add_argument(
        "--job", help="Single job description text (inline)"
    )
    parser.add_argument(
        "--jobs", help="Directory of .txt job description files (batch mode)"
    )
    parser.add_argument(
        "--output", help="Path to write JSON results"
    )
    parser.add_argument(
        "--vault-url",
        default="https://ai102-kvt2-eus.vault.azure.net/",
        help="Key Vault URI",
    )
    parser.add_argument(
        "--deployment",
        default="gpt-4o-mini",
        help="Azure OpenAI deployment name",
    )
    parser.add_argument(
        "--auth",
        choices=["key", "identity"],
        default="key",
        help="Auth mode: 'key' uses Key Vault secrets, 'identity' uses DefaultAzureCredential directly",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )

    # Job search arguments
    parser.add_argument(
        "--search-company", help="Company name to search (triggers search mode)"
    )
    parser.add_argument(
        "--search-keywords", help="Job title keywords for search"
    )
    parser.add_argument(
        "--search-location", help="Location filter for search"
    )
    parser.add_argument(
        "--search-date",
        choices=["all", "today", "3days", "week", "month"],
        default="week",
        help="Date posted filter (default: week)",
    )
    parser.add_argument(
        "--search-type",
        choices=["fulltime", "parttime", "contractor", "intern"],
        help="Employment type filter",
    )
    parser.add_argument(
        "--search-limit", type=int, default=10, help="Max search results (default: 10)"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not args.job and not args.jobs and not args.search_company:
        parser.error("Provide --job (single), --jobs (directory), or --search-company (web search)")

    use_identity = args.auth == "identity"

    # Retrieve secrets from Key Vault
    logger.info("Retrieving secrets from Key Vault...")
    secrets = _get_secrets(args.vault_url)

    # Parse resume
    logger.info("Parsing resume: %s", args.resume)
    profile = parse_resume(
        pdf_path=args.resume,
        doc_intel_endpoint=secrets["doc-intel-endpoint"],
        doc_intel_key=secrets.get("doc-intel-key"),
        openai_endpoint=secrets["openai-endpoint"],
        openai_key=secrets.get("openai-key"),
        deployment_name=args.deployment,
        use_identity=use_identity,
        cache_dir="data/evaluation",
    )
    print(f"\nResume Profile: {profile.summary}\n")

    # Classify jobs
    results = []

    if args.job:
        # Single inline job
        result = score_job(profile, args.job, secrets, args.deployment, use_identity)
        entry = result.model_dump()
        entry["filename"] = "inline"
        results.append(entry)

    if args.jobs:
        # Batch mode
        job_files = _load_job_files(args.jobs)
        for filename, jd_text in job_files:
            logger.info("Classifying: %s", filename)
            try:
                result = score_job(profile, jd_text, secrets, args.deployment, use_identity)
                entry = result.model_dump()
                entry["filename"] = filename
                results.append(entry)
            except Exception as e:
                logger.error("Failed to classify %s: %s", filename, e)
                results.append({"filename": filename, "error": str(e)})

    if args.search_company:
        # Web search mode
        filters = JobSearchFilters(
            company=args.search_company,
            keywords=args.search_keywords,
            location=args.search_location,
            date_posted=args.search_date,
            employment_type=args.search_type,
            max_results=args.search_limit,
        )
        logger.info("Searching jobs: %s", filters.company)
        rapidapi_key = secrets.get("rapidapi-key")
        listings = fetch_jobs(filters, api_key=rapidapi_key)
        print(f"Found {len(listings)} job listing(s)\n")

        for listing in listings:
            logger.info("Classifying: %s at %s", listing.title, listing.company)
            try:
                result = score_job(profile, listing.description, secrets, args.deployment, use_identity)
                entry = result.model_dump()
                entry["filename"] = listing.title
                results.append(entry)
            except Exception as e:
                logger.error("Failed to classify '%s': %s", listing.title, e)
                results.append({"filename": listing.title, "error": str(e)})

    # Output results
    print("\n" + _format_results_table(results))

    # Category summary
    from collections import Counter

    cat_counts = Counter(r.get("category_name", "error") for r in results)
    print("\nCategory Distribution:")
    for cat, count in cat_counts.most_common():
        print(f"  {cat}: {count}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2))
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
