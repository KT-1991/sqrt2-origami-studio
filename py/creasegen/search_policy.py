from __future__ import annotations

from typing import Optional, Tuple


ScoreTuple = Tuple[int, int, int, float, float, float]
PriorityCornerTuple = Tuple[int, float]


def solved_by_score(
    score: ScoreTuple,
    priority_corner_kawasaki: PriorityCornerTuple,
    *,
    require_corner_kawasaki: bool,
) -> bool:
    return (
        score[0] == 0
        and score[1] == 0
        and score[2] == 0
        and (priority_corner_kawasaki[0] == 0 or not require_corner_kawasaki)
    )


def prune_reason(
    score: ScoreTuple,
    *,
    depth: int,
    max_depth: int,
    allow_violations: int,
) -> Optional[str]:
    if depth >= max_depth:
        return "max_depth"
    if score[0] == 0 and score[1] <= allow_violations and score[2] == 0:
        return "allow_violations"
    return None


def refresh_acceptable(
    before_score: ScoreTuple,
    before_priority_corner_kawasaki: PriorityCornerTuple,
    after_score: ScoreTuple,
    after_priority_corner_kawasaki: PriorityCornerTuple,
    *,
    require_corner_kawasaki: bool,
) -> bool:
    return (
        after_score <= before_score
        and (
            not require_corner_kawasaki
            or after_priority_corner_kawasaki[0] <= before_priority_corner_kawasaki[0]
        )
    )


def priority_corner_nonworse(
    before_priority_corner_kawasaki: PriorityCornerTuple,
    after_priority_corner_kawasaki: PriorityCornerTuple,
) -> bool:
    return after_priority_corner_kawasaki[0] <= before_priority_corner_kawasaki[0]


def score_reject_reason(
    parent_score: ScoreTuple,
    child_score: ScoreTuple,
    *,
    margin: int,
) -> Optional[str]:
    if child_score[0] > parent_score[0] + margin:
        return "kawasaki"
    if child_score[1] > parent_score[1] + margin:
        return "corner"
    if child_score[2] > parent_score[2] + margin:
        return "lowline"
    return None


def child_sort_key(
    parent_score: ScoreTuple,
    child_score: ScoreTuple,
    move_tier: int,
) -> Tuple[int, int, int, int, int, float, float, float]:
    k_increase = 1 if child_score[0] > parent_score[0] else 0
    return (k_increase, move_tier, *child_score)
