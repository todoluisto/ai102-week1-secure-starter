"""Evaluation script for the Job Opportunity Scorer.

Runs all sample job descriptions through the classifier, compares
predicted categories against ground truth (encoded in filenames),
and computes accuracy metrics.

Filename convention: <category>_<seq>.txt
    strong_fit_01.txt    → expected category 1
    stretch_role_01.txt  → expected category 2
    interesting_01.txt   → expected category 3
    needs_research_01.txt → expected category 4
    not_relevant_01.txt  → expected category 5

Usage:
    # Run full evaluation (requires Azure resources deployed)
    pytest tests/test_scorer.py -v --run-eval

    # Run as standalone script
    python -m tests.test_scorer --resume data/my_resume.pdf --vault-url https://ai102-kvt2-eus.vault.azure.net/
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import pytest

logger = logging.getLogger(__name__)

# Map filename prefix to expected category ID
PREFIX_TO_CATEGORY = {
    "strong_fit": 1,
    "stretch_role": 2,
    "interesting": 3,
    "needs_research": 4,
    "not_relevant": 5,
}

CATEGORY_NAMES = {
    1: "Strong Fit — Apply Now",
    2: "Stretch Role — Worth a Shot",
    3: "Interesting — Not Now",
    4: "Needs More Research",
    5: "Not Relevant",
}


def get_expected_category(filename: str) -> int | None:
    """Extract expected category ID from filename prefix."""
    stem = Path(filename).stem
    for prefix, cat_id in PREFIX_TO_CATEGORY.items():
        if stem.startswith(prefix):
            return cat_id
    return None


def compute_metrics(results: list[dict]) -> dict:
    """Compute accuracy, per-category precision/recall/F1, and confusion matrix.

    Args:
        results: List of dicts with 'expected' and 'predicted' keys.

    Returns:
        Dict with overall_accuracy, per_category metrics, and confusion_matrix.
    """
    total = len(results)
    correct = sum(1 for r in results if r["expected"] == r["predicted"])
    overall_accuracy = correct / total if total > 0 else 0.0

    # Per-category metrics
    per_category = {}
    for cat_id in range(1, 6):
        tp = sum(1 for r in results if r["expected"] == cat_id and r["predicted"] == cat_id)
        fp = sum(1 for r in results if r["expected"] != cat_id and r["predicted"] == cat_id)
        fn = sum(1 for r in results if r["expected"] == cat_id and r["predicted"] != cat_id)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        per_category[CATEGORY_NAMES[cat_id]] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": sum(1 for r in results if r["expected"] == cat_id),
        }

    # Confusion matrix (5x5)
    confusion = [[0] * 5 for _ in range(5)]
    for r in results:
        if 1 <= r["expected"] <= 5 and 1 <= r["predicted"] <= 5:
            confusion[r["expected"] - 1][r["predicted"] - 1] += 1

    # Confidence calibration
    confidence_accuracy = {}
    for level in ["high", "medium", "low"]:
        subset = [r for r in results if r.get("confidence") == level]
        if subset:
            acc = sum(1 for r in subset if r["expected"] == r["predicted"]) / len(subset)
            confidence_accuracy[level] = {"accuracy": round(acc, 3), "count": len(subset)}

    return {
        "overall_accuracy": round(overall_accuracy, 3),
        "total_samples": total,
        "correct": correct,
        "per_category": per_category,
        "confusion_matrix": confusion,
        "confusion_labels": [CATEGORY_NAMES[i] for i in range(1, 6)],
        "confidence_calibration": confidence_accuracy,
    }


def print_metrics(metrics: dict):
    """Print evaluation metrics to stdout."""
    print(f"\n{'='*60}")
    print(f"EVALUATION RESULTS")
    print(f"{'='*60}")
    print(f"Overall Accuracy: {metrics['overall_accuracy']:.1%} ({metrics['correct']}/{metrics['total_samples']})")

    print(f"\n{'─'*60}")
    print("Per-Category Metrics:")
    print(f"{'Category':<35} {'Prec':>6} {'Rec':>6} {'F1':>6} {'N':>4}")
    print(f"{'─'*60}")
    for name, m in metrics["per_category"].items():
        print(f"{name:<35} {m['precision']:>6.3f} {m['recall']:>6.3f} {m['f1']:>6.3f} {m['support']:>4d}")

    print(f"\n{'─'*60}")
    print("Confusion Matrix (rows=expected, cols=predicted):")
    labels = metrics["confusion_labels"]
    # Print short labels
    short = ["Fit", "Stretch", "Intrstn", "Rsrch", "N/A"]
    print(f"{'':>12}", end="")
    for s in short:
        print(f"{s:>8}", end="")
    print()
    for i, row in enumerate(metrics["confusion_matrix"]):
        print(f"{short[i]:>12}", end="")
        for val in row:
            print(f"{val:>8}", end="")
        print()

    if metrics.get("confidence_calibration"):
        print(f"\n{'─'*60}")
        print("Confidence Calibration:")
        for level, data in metrics["confidence_calibration"].items():
            print(f"  {level}: {data['accuracy']:.1%} accuracy ({data['count']} samples)")


# ─── Pytest integration ──────────────────────────────────────────

@pytest.fixture
def eval_flag(request):
    return request.config.getoption("--run-eval")


class TestScorerMetrics:
    """Unit tests for the metrics computation (no Azure needed)."""

    def test_compute_metrics_perfect(self):
        results = [
            {"expected": i, "predicted": i, "confidence": "high"}
            for i in range(1, 6)
        ]
        metrics = compute_metrics(results)
        assert metrics["overall_accuracy"] == 1.0
        assert metrics["correct"] == 5

    def test_compute_metrics_all_wrong(self):
        results = [
            {"expected": 1, "predicted": 5, "confidence": "low"},
            {"expected": 2, "predicted": 4, "confidence": "low"},
        ]
        metrics = compute_metrics(results)
        assert metrics["overall_accuracy"] == 0.0

    def test_get_expected_category(self):
        assert get_expected_category("strong_fit_01.txt") == 1
        assert get_expected_category("stretch_role_03.txt") == 2
        assert get_expected_category("interesting_02.txt") == 3
        assert get_expected_category("needs_research_01.txt") == 4
        assert get_expected_category("not_relevant_07.txt") == 5
        assert get_expected_category("unknown_file.txt") is None

    def test_confidence_calibration(self):
        results = [
            {"expected": 1, "predicted": 1, "confidence": "high"},
            {"expected": 1, "predicted": 2, "confidence": "low"},
        ]
        metrics = compute_metrics(results)
        assert metrics["confidence_calibration"]["high"]["accuracy"] == 1.0
        assert metrics["confidence_calibration"]["low"]["accuracy"] == 0.0


# ─── Standalone evaluation runner ────────────────────────────────

def run_evaluation(resume_path: str, vault_url: str, jobs_dir: str, output_path: str):
    """Run full evaluation: classify all sample JDs and compute metrics."""
    from src.resume_parser import parse_resume
    from src.scorer import _get_secrets, score_job

    secrets = _get_secrets(vault_url)

    profile = parse_resume(
        pdf_path=resume_path,
        doc_intel_endpoint=secrets["doc-intel-endpoint"],
        doc_intel_key=secrets.get("doc-intel-key"),
        openai_endpoint=secrets["openai-endpoint"],
        openai_key=secrets.get("openai-key"),
        cache_dir="data/evaluation",
    )

    jobs_path = Path(jobs_dir)
    job_files = sorted(jobs_path.glob("*.txt"))

    results = []
    for jf in job_files:
        expected = get_expected_category(jf.name)
        if expected is None:
            logger.warning("Skipping %s — no expected category in filename", jf.name)
            continue

        logger.info("Classifying: %s (expected: %d)", jf.name, expected)
        try:
            result = score_job(profile, jf.read_text().strip(), secrets)
            results.append({
                "filename": jf.name,
                "expected": expected,
                "predicted": result.category_id,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "skills_match_pct": result.skills_match_pct,
            })
        except Exception as e:
            logger.error("Failed: %s — %s", jf.name, e)
            results.append({
                "filename": jf.name,
                "expected": expected,
                "predicted": -1,
                "confidence": "error",
                "error": str(e),
            })

    metrics = compute_metrics(results)
    print_metrics(metrics)

    # Find misclassifications
    misses = [r for r in results if r["expected"] != r["predicted"]]
    if misses:
        print(f"\n{'─'*60}")
        print(f"Misclassifications ({len(misses)}):")
        for m in misses:
            print(f"  {m['filename']}: expected {m['expected']}, got {m['predicted']} ({m.get('confidence', '?')})")
            if m.get("reasoning"):
                print(f"    Reasoning: {m['reasoning']}")

    # Save full results
    output = {
        "metrics": metrics,
        "classifications": results,
        "misclassifications": misses,
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, indent=2))
    print(f"\nFull results written to {output_path}")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run evaluation on sample job descriptions")
    parser.add_argument("--resume", required=True, help="Path to resume PDF")
    parser.add_argument("--vault-url", default="https://ai102-kvt2-eus.vault.azure.net/")
    parser.add_argument("--jobs-dir", default="data/sample_jobs/")
    parser.add_argument("--output", default="data/evaluation/results.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_evaluation(args.resume, args.vault_url, args.jobs_dir, args.output)
