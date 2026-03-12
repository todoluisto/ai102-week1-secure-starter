"""Unit tests for Cosmos DB store module (mocked — no Azure needed)."""

from unittest.mock import MagicMock, patch

import pytest

from src.cosmos_store import (
    _build_doc_id,
    query_results,
    result_exists,
    upsert_job_result,
)


# ─── _build_doc_id ────────────────────────────────────────────────
class TestBuildDocId:
    def test_deterministic(self):
        """Same inputs always produce the same ID."""
        id1 = _build_doc_id("Engineer", "Acme", "https://example.com/1")
        id2 = _build_doc_id("Engineer", "Acme", "https://example.com/1")
        assert id1 == id2

    def test_length(self):
        """ID is 16 hex characters."""
        doc_id = _build_doc_id("Engineer", "Acme", "https://example.com/1")
        assert len(doc_id) == 16
        assert all(c in "0123456789abcdef" for c in doc_id)

    def test_unique_for_different_titles(self):
        """Different titles produce different IDs."""
        id1 = _build_doc_id("Senior Engineer", "Acme", "https://example.com/1")
        id2 = _build_doc_id("Junior Engineer", "Acme", "https://example.com/1")
        assert id1 != id2

    def test_unique_for_different_companies(self):
        """Different companies produce different IDs."""
        id1 = _build_doc_id("Engineer", "Acme", "https://example.com/1")
        id2 = _build_doc_id("Engineer", "Globex", "https://example.com/1")
        assert id1 != id2

    def test_unique_for_different_urls(self):
        """Different URLs produce different IDs."""
        id1 = _build_doc_id("Engineer", "Acme", "https://example.com/1")
        id2 = _build_doc_id("Engineer", "Acme", "https://example.com/2")
        assert id1 != id2


# ─── upsert_job_result ────────────────────────────────────────────
class TestUpsertJobResult:
    @patch("src.cosmos_store._get_container")
    def test_entity_shape(self, mock_get_container):
        """Verify the upserted document has all expected fields."""
        mock_container = MagicMock()
        mock_container.upsert_item.side_effect = lambda doc: doc
        mock_get_container.return_value = mock_container

        listing = {
            "title": "Data Engineer",
            "company": "Microsoft",
            "location": "Redmond, WA",
            "url": "https://example.com/job/1",
            "date_posted": "2026-03-08",
            "employment_type": "FULLTIME",
            "source": "LinkedIn",
        }
        classification = {
            "category_id": 1,
            "category_name": "Strong Fit — Apply Now",
            "confidence": "high",
            "reasoning": "Great match",
            "skills_match_pct": 85,
            "suggested_action": "Apply immediately",
        }
        gap = {
            "matched_skills": [{"name": "Python"}, {"name": "SQL"}],
            "missing_skills": [{"name": "Spark"}],
            "summary": "Strong match with minor gaps",
            "recommendations": ["Learn Spark"],
        }

        result = upsert_job_result(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            listing=listing,
            classification=classification,
            gap=gap,
            search_query="Microsoft data engineer",
            run_date="2026-03-11",
        )

        # Verify required fields
        assert result["company"] == "Microsoft"
        assert result["title"] == "Data Engineer"
        assert result["category_id"] == 1
        assert result["category_name"] == "Strong Fit — Apply Now"
        assert result["skills_match_pct"] == 85
        assert result["matched_skills_count"] == 2
        assert result["missing_skills_count"] == 1
        assert result["search_query"] == "Microsoft data engineer"
        assert result["run_date"] == "2026-03-11"
        assert "id" in result
        assert "run_timestamp" in result

    @patch("src.cosmos_store._get_container")
    def test_upsert_calls_container(self, mock_get_container):
        """Verify upsert_item is called on the container."""
        mock_container = MagicMock()
        mock_container.upsert_item.side_effect = lambda doc: doc
        mock_get_container.return_value = mock_container

        upsert_job_result(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            listing={"title": "X", "company": "Y", "url": "Z"},
            classification={"category_id": 1},
            gap={"matched_skills": [], "missing_skills": []},
            search_query="test",
            run_date="2026-03-11",
        )

        mock_container.upsert_item.assert_called_once()


# ─── query_results ────────────────────────────────────────────────
class TestQueryResults:
    @patch("src.cosmos_store._get_container")
    def test_no_filters(self, mock_get_container):
        """Query with no filters returns all items."""
        mock_container = MagicMock()
        mock_container.query_items.return_value = [{"id": "1"}, {"id": "2"}]
        mock_get_container.return_value = mock_container

        results = query_results(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
        )

        assert len(results) == 2
        mock_container.query_items.assert_called_once()

    @patch("src.cosmos_store._get_container")
    def test_with_date_filter(self, mock_get_container):
        """Query with date filters builds correct query."""
        mock_container = MagicMock()
        mock_container.query_items.return_value = []
        mock_get_container.return_value = mock_container

        query_results(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            date_from="2026-03-01",
            date_to="2026-03-11",
        )

        call_kwargs = mock_container.query_items.call_args
        query = call_kwargs.kwargs.get("query") or call_kwargs[1].get("query")
        assert "@date_from" in query
        assert "@date_to" in query

    @patch("src.cosmos_store._get_container")
    def test_with_company_filter(self, mock_get_container):
        """Query with company filter uses partition key."""
        mock_container = MagicMock()
        mock_container.query_items.return_value = []
        mock_get_container.return_value = mock_container

        query_results(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            company="Microsoft",
        )

        call_kwargs = mock_container.query_items.call_args
        query = call_kwargs.kwargs.get("query") or call_kwargs[1].get("query")
        assert "@company" in query
        # When company is specified, cross-partition should be False
        enable_cross = call_kwargs.kwargs.get("enable_cross_partition_query")
        assert enable_cross is False

    @patch("src.cosmos_store._get_container")
    def test_with_category_filter(self, mock_get_container):
        """Query with category filter includes category in query."""
        mock_container = MagicMock()
        mock_container.query_items.return_value = []
        mock_get_container.return_value = mock_container

        query_results(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            category=1,
        )

        call_kwargs = mock_container.query_items.call_args
        query = call_kwargs.kwargs.get("query") or call_kwargs[1].get("query")
        assert "@category" in query


# ─── result_exists ────────────────────────────────────────────────
class TestResultExists:
    @patch("src.cosmos_store._get_container")
    def test_exists(self, mock_get_container):
        """Returns True when document exists."""
        mock_container = MagicMock()
        mock_container.read_item.return_value = {"id": "abc123"}
        mock_get_container.return_value = mock_container

        assert result_exists(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            doc_id="abc123",
            company="Microsoft",
        )

    @patch("src.cosmos_store._get_container")
    def test_not_exists(self, mock_get_container):
        """Returns False when document doesn't exist (raises exception)."""
        mock_container = MagicMock()
        mock_container.read_item.side_effect = Exception("Not found")
        mock_get_container.return_value = mock_container

        assert not result_exists(
            endpoint="https://fake.documents.azure.com:443/",
            credential=MagicMock(),
            db="jobscorer",
            container="results",
            doc_id="nonexistent",
            company="Microsoft",
        )
