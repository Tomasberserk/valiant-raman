"""Evaluator module analyzing learning return and cost-efficiency per experiment."""

from typing import Any, Dict, List
from engine.experiments.models import Experiment, Render


class ExperimentEvaluator:
    """Analyzes experiment execution and performance metrics across variants."""

    @staticmethod
    def evaluate_run_performance(renders: List[Render]) -> Dict[str, Any]:
        """Compute operational and quality metrics for an experiment run."""
        total_renders = len(renders)
        if total_renders == 0:
            return {"status": "no_renders"}

        qa_passed_count = sum(1 for r in renders if r.qa_passed)
        qa_pass_rate = round(qa_passed_count / total_renders, 2)
        total_duration = sum(r.duration_seconds for r in renders)
        total_render_time = sum(r.render_time_seconds for r in renders)

        render_efficiency = (
            round(total_render_time / total_duration, 2) if total_duration > 0 else 0.0
        )

        return {
            "total_renders": total_renders,
            "qa_passed_count": qa_passed_count,
            "qa_pass_rate": qa_pass_rate,
            "total_duration_sec": round(total_duration, 2),
            "total_render_time_sec": round(total_render_time, 2),
            "render_time_ratio": render_efficiency,
        }

    @staticmethod
    def compare_variants_metrics(experiment: Experiment) -> List[Dict[str, Any]]:
        """Compare distribution and retention metrics across variants (A vs B vs C)."""
        comparison: List[Dict[str, Any]] = []

        for hyp in experiment.hypotheses:
            for var in hyp.variants:
                for render in var.renders:
                    for pub in render.publications:
                        for m in pub.metrics:
                            comparison.append({
                                "variant_code": var.variant_code,
                                "hook_type": var.hook_type,
                                "platform": pub.platform,
                                "views": m.views,
                                "retention_at_3s": m.retention_at_3s,
                                "completion_rate": m.completion_rate,
                            })

        return comparison
