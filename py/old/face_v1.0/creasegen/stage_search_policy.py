from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


ScoreTuple = Tuple[int, int, int, float, float, float]


@dataclass(frozen=True)
class CoarseRoundStatus:
    improved: bool
    solved: bool


def evaluate_coarse_round(
    *,
    base_score: ScoreTuple,
    best_score: ScoreTuple,
) -> CoarseRoundStatus:
    improved = best_score < base_score
    solved = best_score[0] == 0 and best_score[1] == 0 and best_score[2] == 0
    return CoarseRoundStatus(improved=improved, solved=solved)


def record_stage_iter_limit(stats: Dict[str, int]) -> None:
    stats["stage_iter_limit"] = stats.get("stage_iter_limit", 0) + 1


def record_coarse_round_improved(stats: Dict[str, int]) -> None:
    stats["coarse_round_improved"] = stats.get("coarse_round_improved", 0) + 1


def record_coarse_round_stalled(stats: Dict[str, int]) -> None:
    stats["coarse_round_stalled"] = stats.get("coarse_round_stalled", 0) + 1


def update_stall_round_need_max(stats: Dict[str, int], stall_need: int) -> None:
    stats["stall_round_need_max"] = max(
        stats.get("stall_round_need_max", 0),
        stall_need,
    )


def can_trigger_auto_expand(
    *,
    rounds: int,
    auto_expand_max_rounds: int,
    stats: Dict[str, int],
) -> bool:
    if rounds >= max(0, auto_expand_max_rounds):
        stats["auto_expand_round_limit"] = stats.get("auto_expand_round_limit", 0) + 1
        return False
    return True


def record_auto_expand_trigger(stats: Dict[str, int]) -> None:
    stats["auto_expand_trigger"] = stats.get("auto_expand_trigger", 0) + 1


def record_auto_expand_mode(stats: Dict[str, int], mode: str) -> None:
    if mode == "k_only":
        stats["auto_expand_k_only"] = stats.get("auto_expand_k_only", 0) + 1
        return
    stats["auto_expand_with_ab"] = stats.get("auto_expand_with_ab", 0) + 1
