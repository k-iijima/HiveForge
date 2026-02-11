"""Referee Bee: Differential Testing

候補間の出力差分を比較する。
同一入力を各候補に投入し、出力の一致/不一致を判定する。
"""

from __future__ import annotations

import itertools
from typing import Any

from .models import DiffResult


class DiffTester:
    """Differential Testing実行器

    候補の出力辞書を比較し、DiffResultのリストを返す。
    """

    def compare(
        self,
        candidates: dict[str, dict[str, Any]],
        input_description: str,
    ) -> list[DiffResult]:
        """候補間のペアワイズ比較

        Args:
            candidates: {candidate_id: output_dict} のマッピング
            input_description: 入力の説明

        Returns:
            ペアごとのDiffResult
        """
        results: list[DiffResult] = []
        candidate_ids = sorted(candidates.keys())

        for id_a, id_b in itertools.combinations(candidate_ids, 2):
            output_a = candidates[id_a]
            output_b = candidates[id_b]
            match = output_a == output_b

            diff_details: dict[str, Any] = {}
            if not match:
                diff_details = {
                    "candidate_a_output": str(output_a),
                    "candidate_b_output": str(output_b),
                }

            results.append(
                DiffResult(
                    candidate_a=id_a,
                    candidate_b=id_b,
                    input_description=input_description,
                    outputs_match=match,
                    diff_details=diff_details,
                )
            )

        return results

    def consistency_ratio(self, results: list[DiffResult]) -> float:
        """一致率を計算

        Returns:
            一致ペア / 全ペア。結果が空なら1.0。
        """
        if not results:
            return 1.0

        matched = sum(1 for r in results if r.outputs_match)
        return matched / len(results)
