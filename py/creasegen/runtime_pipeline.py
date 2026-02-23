from __future__ import annotations

from typing import Dict, Sequence

from creasegen.core_types import PointE
from creasegen.run_config import RunConfig
from creasegen.runtime_context import RunAppContext
from creasegen.app import run_app as _run_app_impl
from creasegen import runtime_ops as ops


def run(
    corners: Sequence[PointE],
    config: RunConfig,
) -> Dict[str, object]:
    return _run_app_impl(corners=corners, config=config, ctx=_RUN_APP_CONTEXT)


def _build_run_app_context() -> RunAppContext:
    bindings: Dict[str, object] = {}
    for field_name in RunAppContext.__dataclass_fields__:
        if not hasattr(ops, field_name):
            raise AttributeError(f"runtime_ops is missing required context binding: {field_name}")
        bindings[field_name] = getattr(ops, field_name)
    return RunAppContext(**bindings)


_RUN_APP_CONTEXT = _build_run_app_context()

