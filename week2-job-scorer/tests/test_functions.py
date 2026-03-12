"""Unit tests for Azure Function HTTP triggers (mocked — no Azure needed)."""

import json
from unittest.mock import MagicMock, patch

import azure.functions as func
import pytest


# ─── Helper to create mock HttpRequest ────────────────────────────
def _make_request(method="GET", body=None, params=None, route_params=None):
    """Create a mock Azure Functions HttpRequest."""
    return func.HttpRequest(
        method=method,
        url="http://localhost:7071/api/test",
        headers={"Content-Type": "application/json"},
        params=params or {},
        route_params=route_params or {},
        body=json.dumps(body).encode() if body else b"",
    )


# ─── Classify Endpoint ───────────────────────────────────────────
class TestClassifyEndpoint:
    @patch("functions.function_app._load_resume_profile")
    @patch("functions.function_app._get_cached_secrets")
    @patch("functions.function_app.score_job_with_gap")
    def test_classify_success(self, mock_score, mock_secrets, mock_profile):
        """Successful classification returns 200 with results."""
        from functions.function_app import classify_job

        mock_classification = MagicMock()
        mock_classification.model_dump.return_value = {
            "category_id": 1,
            "category_name": "Strong Fit — Apply Now",
            "confidence": "high",
            "reasoning": "Great match",
            "skills_match_pct": 85,
            "suggested_action": "Apply now",
        }
        mock_gap = MagicMock()
        mock_gap.model_dump.return_value = {
            "matched_skills": [],
            "missing_skills": [],
            "bonus_skills": [],
            "summary": "Good fit",
            "recommendations": [],
        }
        mock_score.return_value = (mock_classification, mock_gap)
        mock_secrets.return_value = {"openai-key": "test"}
        mock_profile.return_value = MagicMock()

        req = _make_request(method="POST", body={"job_description": "Test JD"})
        resp = classify_job(req)

        assert resp.status_code == 200
        data = json.loads(resp.get_body())
        assert "classification" in data
        assert "gap" in data
        assert data["classification"]["category_id"] == 1

    def test_classify_missing_body(self):
        """Missing job_description returns 400."""
        from functions.function_app import classify_job

        req = _make_request(method="POST", body={"job_description": ""})
        resp = classify_job(req)

        assert resp.status_code == 400

    def test_classify_invalid_json(self):
        """Invalid JSON body returns 400."""
        from functions.function_app import classify_job

        req = func.HttpRequest(
            method="POST",
            url="http://localhost:7071/api/jobs/classify",
            headers={},
            params={},
            route_params={},
            body=b"not json",
        )
        resp = classify_job(req)

        assert resp.status_code == 400


# ─── Search Endpoint ─────────────────────────────────────────────
class TestSearchEndpoint:
    @patch("functions.function_app._get_cached_secrets")
    @patch("functions.function_app.fetch_jobs")
    def test_search_success(self, mock_fetch, mock_secrets):
        """Successful search returns list of listings."""
        from functions.function_app import search_jobs

        mock_listing = MagicMock()
        mock_listing.model_dump.return_value = {
            "title": "Data Engineer",
            "company": "Microsoft",
            "location": "Redmond",
            "description": "...",
            "url": "https://example.com",
            "date_posted": "2026-03-08",
            "employment_type": "FULLTIME",
            "source": "LinkedIn",
        }
        mock_fetch.return_value = [mock_listing]
        mock_secrets.return_value = {"rapidapi-key": "test"}

        req = _make_request(
            method="POST",
            body={"company": "Microsoft", "keywords": "data engineer"},
        )
        resp = search_jobs(req)

        assert resp.status_code == 200
        data = json.loads(resp.get_body())
        assert len(data) == 1
        assert data[0]["company"] == "Microsoft"

    def test_search_invalid_json(self):
        """Invalid JSON body returns 400."""
        from functions.function_app import search_jobs

        req = func.HttpRequest(
            method="POST",
            url="http://localhost:7071/api/jobs/search",
            headers={},
            params={},
            route_params={},
            body=b"bad",
        )
        resp = search_jobs(req)

        assert resp.status_code == 400


# ─── Results Endpoint ────────────────────────────────────────────
class TestResultsEndpoint:
    @patch("functions.function_app._get_cosmos_config")
    @patch("functions.function_app.query_results")
    def test_results_success(self, mock_query, mock_config):
        """Successful query returns results."""
        from functions.function_app import get_results

        mock_config.return_value = (
            "https://fake.documents.azure.com:443/",
            MagicMock(),
            "jobscorer",
            "results",
        )
        mock_query.return_value = [
            {"id": "abc", "company": "Microsoft", "title": "Data Engineer"},
        ]

        req = _make_request(params={"date_from": "2026-03-01"})
        resp = get_results(req)

        assert resp.status_code == 200
        data = json.loads(resp.get_body())
        assert len(data) == 1

    @patch("functions.function_app._get_cosmos_config")
    @patch("functions.function_app.query_results")
    def test_results_with_filters(self, mock_query, mock_config):
        """Query params are passed through to query_results."""
        from functions.function_app import get_results

        mock_config.return_value = (
            "https://fake.documents.azure.com:443/",
            MagicMock(),
            "jobscorer",
            "results",
        )
        mock_query.return_value = []

        req = _make_request(params={
            "date_from": "2026-03-01",
            "date_to": "2026-03-11",
            "company": "Google",
            "category": "2",
        })
        resp = get_results(req)

        assert resp.status_code == 200
        mock_query.assert_called_once_with(
            endpoint="https://fake.documents.azure.com:443/",
            credential=mock_config.return_value[1],
            db="jobscorer",
            container="results",
            date_from="2026-03-01",
            date_to="2026-03-11",
            company="Google",
            category=2,
        )


# ─── Health Endpoint ─────────────────────────────────────────────
class TestHealthEndpoint:
    @patch("functions.function_app._read_blob_json")
    @patch("functions.function_app.query_results")
    @patch("functions.function_app._get_cosmos_config")
    @patch("functions.function_app._get_cached_secrets")
    def test_health_all_ok(self, mock_secrets, mock_config, mock_query, mock_blob):
        """Health check returns ok when all services are healthy."""
        from functions.function_app import health

        mock_secrets.return_value = {"test": "ok"}
        mock_config.return_value = ("endpoint", MagicMock(), "db", "container")
        mock_query.return_value = []
        mock_blob.return_value = {}

        req = _make_request()
        resp = health(req)

        assert resp.status_code == 200
        data = json.loads(resp.get_body())
        assert data["status"] == "ok"
        assert data["services"]["key_vault"] == "ok"
        assert data["services"]["cosmos_db"] == "ok"
        assert data["services"]["blob_storage"] == "ok"

    @patch("functions.function_app._read_blob_json")
    @patch("functions.function_app.query_results")
    @patch("functions.function_app._get_cosmos_config")
    @patch("functions.function_app._get_cached_secrets")
    def test_health_degraded(self, mock_secrets, mock_config, mock_query, mock_blob):
        """Health check returns degraded when a service is down."""
        from functions.function_app import health

        mock_secrets.side_effect = Exception("vault unreachable")
        mock_config.return_value = ("endpoint", MagicMock(), "db", "container")
        mock_query.return_value = []
        mock_blob.return_value = {}

        req = _make_request()
        resp = health(req)

        assert resp.status_code == 200
        data = json.loads(resp.get_body())
        assert data["status"] == "degraded"
        assert "error" in data["services"]["key_vault"]
