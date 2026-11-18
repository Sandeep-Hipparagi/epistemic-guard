from __future__ import annotations

import json
from pathlib import Path
import pytest

from benchmarks.evaluate import evaluate_dataset
from epistemic_guard.schemas import ExtractedClaim
from epistemic_guard.tools.search import SearchHit


class TestBenchmarkEvaluation:
    @pytest.fixture
    def dataset_path(self) -> Path:
        path = Path("benchmarks/dataset.jsonl")
        assert path.is_file(), f"Benchmark dataset not found at {path}"
        return path

    def test_dataset_jsonl_schema_validity(self, dataset_path: Path) -> None:
        """Verify structural validity and schema constraints of the benchmark dataset."""
        required_root_keys = {
            "id",
            "category",
            "topic",
            "discourse_inputs",
            "extracted_claims",
            "mock_search_hits",
            "reference_now_iso",
            "expected",
        }
        required_expected_keys = {
            "expected_shareable",
            "expected_verdict",
            "expected_recycled",
            "expected_asymmetry",
        }

        cases = []
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    continue

                case = json.loads(clean_line)
                missing_root = required_root_keys - case.keys()
                assert not missing_root, f"Line {line_no} ({case.get('id')}) missing keys: {missing_root}"

                missing_exp = required_expected_keys - case["expected"].keys()
                assert not missing_exp, f"Line {line_no} ({case.get('id')}) missing expected keys: {missing_exp}"

                assert isinstance(case["discourse_inputs"], list) and len(case["discourse_inputs"]) >= 1
                assert isinstance(case["extracted_claims"], list) and len(case["extracted_claims"]) >= 1

                # Validate Pydantic deserialization
                for raw_claim in case["extracted_claims"]:
                    claim_obj = ExtractedClaim(**raw_claim)
                    assert claim_obj.claim_id
                    assert claim_obj.normalized_claim

                for raw_hit in case["mock_search_hits"]:
                    hit_obj = SearchHit(**raw_hit)
                    assert hit_obj.url
                    assert hit_obj.source_query

                cases.append(case)

        assert len(cases) >= 12, f"Expected at least 12 benchmark cases, found {len(cases)}"

    def test_benchmark_evaluation_harness_pass_rate(self, dataset_path: Path) -> None:
        """Execute end-to-end benchmark harness and verify precision/recall thresholds."""
        metrics = evaluate_dataset(dataset_path)

        assert metrics["total_cases"] >= 12
        assert metrics["failed_cases"] == 0, f"Benchmark had failed cases: {metrics['case_results']}"
        assert metrics["overall_accuracy"] >= 0.95
        assert metrics["misinformation_block_recall"] >= 0.95
        assert metrics["verified_share_precision"] >= 0.95
        assert metrics["temporal_drift_recall"] >= 0.95
        assert metrics["asymmetry_detection_accuracy"] >= 0.95

        # Invariant: Must run 100% offline in under 3.0 seconds
        assert metrics["total_duration_ms"] < 3000.0, f"Benchmark execution too slow: {metrics['total_duration_ms']}ms"

    def test_benchmark_missing_dataset_raises(self) -> None:
        """Verify FileNotFoundError is raised for non-existent dataset paths."""
        with pytest.raises(FileNotFoundError):
            evaluate_dataset("non_existent_dataset_file.jsonl")
