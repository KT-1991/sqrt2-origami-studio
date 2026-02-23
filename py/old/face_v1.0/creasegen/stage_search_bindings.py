from __future__ import annotations

from typing import Dict, Sequence, Tuple

from creasegen.run_config import RunConfig
from creasegen.runtime_context import RunAppContext
from creasegen.stage_search import StageSearchConfig, StageSearchDeps

__all__ = [
    "STAGE_SEARCH_DEP_FIELDS",
    "STAGE_SEARCH_CONFIG_FIELDS",
    "build_stage_search_deps",
    "build_stage_search_config",
]


STAGE_SEARCH_DEP_FIELDS: Tuple[str, ...] = tuple(StageSearchDeps.__dataclass_fields__.keys())
STAGE_SEARCH_CONFIG_FIELDS: Tuple[str, ...] = tuple(StageSearchConfig.__dataclass_fields__.keys())


def build_stage_search_deps(ctx: RunAppContext) -> StageSearchDeps:
    bindings: Dict[str, object] = {}
    for field_name in STAGE_SEARCH_DEP_FIELDS:
        if not hasattr(ctx, field_name):
            raise AttributeError(f"run context is missing stage-search dependency: {field_name}")
        bindings[field_name] = getattr(ctx, field_name)
    return StageSearchDeps(**bindings)


def build_stage_search_config(*, corners: Sequence, config: RunConfig) -> StageSearchConfig:
    values: Dict[str, object] = {}
    for field_name in STAGE_SEARCH_CONFIG_FIELDS:
        if field_name == "corners":
            values[field_name] = corners
            continue
        if not hasattr(config, field_name):
            raise AttributeError(f"run config is missing stage-search field: {field_name}")
        values[field_name] = getattr(config, field_name)
    return StageSearchConfig(**values)
