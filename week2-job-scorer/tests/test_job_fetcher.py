"""Tests for the Job Fetcher module.

Unit tests mock all HTTP calls — no API key needed.
Integration test (gated behind --run-fetch) calls the real JSearch API.

Usage:
    pytest tests/test_job_fetcher.py -v              # unit tests only
    pytest tests/test_job_fetcher.py -v --run-fetch  # includes integration test
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.job_fetcher import (
    JobFetchError,
    JobListing,
    JobSearchFilters,
    _build_jsearch_query,
    _parse_jsearch_response,
    fetch_jobs,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_response():
    """Load the sample JSearch API response."""
    return json.loads((FIXTURES_DIR / "jsearch_sample_response.json").read_text())


# ─── Query Building ──────────────────────────────────────────────


class TestBuildJsearchQuery:
    def test_basic_company_only(self):
        filters = JobSearchFilters(company="Microsoft")
        params = _build_jsearch_query(filters)

        assert params["query"] == "Microsoft"
        assert params["date_posted"] == "week"
        assert "employment_types" not in params

    def test_all_filters(self):
        filters = JobSearchFilters(
            company="Google",
            keywords="data engineer",
            location="New York, NY",
            date_posted="month",
            employment_type="fulltime",
            max_results=20,
        )
        params = _build_jsearch_query(filters)

        assert "Google" in params["query"]
        assert "data engineer" in params["query"]
        assert "New York, NY" in params["query"]
        assert params["date_posted"] == "month"
        assert params["employment_types"] == "FULLTIME"

    def test_keywords_appended_to_query(self):
        filters = JobSearchFilters(company="Amazon", keywords="ML engineer")
        params = _build_jsearch_query(filters)
        assert params["query"] == "Amazon ML engineer"

    def test_location_appended_with_in(self):
        filters = JobSearchFilters(company="Meta", location="Remote")
        params = _build_jsearch_query(filters)
        assert "in Remote" in params["query"]


# ─── Response Parsing ────────────────────────────────────────────


class TestParseJsearchResponse:
    def test_parse_valid_response(self, sample_response):
        listings = _parse_jsearch_response(sample_response)

        # Third listing has empty description, should be skipped
        assert len(listings) == 2

        first = listings[0]
        assert first.title == "Senior Data Engineer"
        assert first.company == "Microsoft"
        assert first.location == "Redmond, WA, US"
        assert "scalable data pipelines" in first.description
        assert first.url == "https://careers.microsoft.com/jobs/12345"
        assert first.employment_type == "FULLTIME"
        assert first.source == "LinkedIn"

    def test_remote_location_formatting(self, sample_response):
        listings = _parse_jsearch_response(sample_response)
        second = listings[1]
        assert second.location.startswith("Remote")

    def test_empty_description_skipped(self, sample_response):
        """The third listing has an empty description and should be skipped."""
        listings = _parse_jsearch_response(sample_response)
        titles = [l.title for l in listings]
        assert "Software Engineer Intern" not in titles

    def test_empty_data(self):
        listings = _parse_jsearch_response({"data": []})
        assert listings == []

    def test_missing_data_key(self):
        listings = _parse_jsearch_response({})
        assert listings == []


# ─── JobListing Validation ───────────────────────────────────────


class TestJobListing:
    def test_has_description(self):
        listing = JobListing(
            title="Engineer",
            company="Acme",
            location="Remote",
            description="Build things with Python and AWS.",
            url="https://example.com/job/1",
            date_posted="2026-03-08",
            employment_type="FULLTIME",
            source="LinkedIn",
        )
        assert len(listing.description) > 0

    def test_model_fields(self):
        assert set(JobListing.model_fields.keys()) == {
            "title", "company", "location", "description",
            "url", "date_posted", "employment_type", "source",
        }


# ─── fetch_jobs (mocked) ────────────────────────────────────────


class TestFetchJobs:
    @patch("src.job_fetcher.requests.get")
    def test_successful_fetch(self, mock_get, sample_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_response
        mock_get.return_value = mock_resp

        filters = JobSearchFilters(company="Microsoft")
        listings = fetch_jobs(filters, api_key="test-key")

        assert len(listings) == 2
        assert listings[0].title == "Senior Data Engineer"
        mock_get.assert_called_once()

    @patch("src.job_fetcher.requests.get")
    def test_empty_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "OK", "data": []}
        mock_get.return_value = mock_resp

        filters = JobSearchFilters(company="NonexistentCorp12345")
        listings = fetch_jobs(filters, api_key="test-key")

        assert listings == []

    @patch("src.job_fetcher.requests.get")
    def test_api_error_raises(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        filters = JobSearchFilters(company="Microsoft")
        with pytest.raises(JobFetchError, match="500"):
            fetch_jobs(filters, api_key="test-key")

    @patch("src.job_fetcher.requests.get")
    def test_rate_limit_raises(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit exceeded"
        mock_get.return_value = mock_resp

        filters = JobSearchFilters(company="Microsoft")
        with pytest.raises(JobFetchError, match="rate limit"):
            fetch_jobs(filters, api_key="test-key")

    @patch("src.job_fetcher.requests.get")
    def test_network_error_raises(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        filters = JobSearchFilters(company="Microsoft")
        with pytest.raises(JobFetchError, match="Network error"):
            fetch_jobs(filters, api_key="test-key")

    def test_missing_api_key_raises(self):
        filters = JobSearchFilters(company="Microsoft")
        with patch.dict("os.environ", {}, clear=True):
            with patch("src.job_fetcher._resolve_api_key", side_effect=JobFetchError("No RapidAPI key")):
                with pytest.raises(JobFetchError, match="No RapidAPI key"):
                    fetch_jobs(filters)

    @patch("src.job_fetcher.requests.get")
    def test_max_results_trimmed(self, mock_get, sample_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_response
        mock_get.return_value = mock_resp

        filters = JobSearchFilters(company="Microsoft", max_results=1)
        listings = fetch_jobs(filters, api_key="test-key")

        assert len(listings) == 1


# ─── Integration test (requires API key) ────────────────────────


@pytest.fixture
def run_fetch(request):
    return request.config.getoption("--run-fetch", default=False)


class TestFetchJobsIntegration:
    def test_live_search(self, run_fetch):
        if not run_fetch:
            pytest.skip("Pass --run-fetch to run integration tests")

        filters = JobSearchFilters(company="Microsoft", keywords="engineer", max_results=3)
        listings = fetch_jobs(filters)

        assert len(listings) > 0
        for listing in listings:
            assert listing.title
            assert listing.company
            assert listing.description
            assert listing.url
