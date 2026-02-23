from __future__ import annotations

import json

from creasegen.cli import build_parser
from creasegen.parsing import parse_corners
from creasegen.run_config import RunConfig
from creasegen.run_request_store import append_run_request, make_run_request_entry
from creasegen.runtime_pipeline import run


def main() -> None:
    # Longer benchmark preset (about ~1 minute on this machine):
    # --max-depth 4 --branch-per-node 3 --max-nodes 9
    # --max-bounces 12 --dir-top-k 4 --priority-top-n 5
    # --auto-expand-grid --no-render
    parser = build_parser()
    args = parser.parse_args()

    corners = parse_corners(args.corners)
    cfg = RunConfig.from_cli_args(args)
    result = run(corners=corners, config=cfg)

    if not args.no_save_run_request:
        run_req = make_run_request_entry(
            profile_name=args.profile_name,
            request=cfg.run_request_payload(args.corners),
        )
        append_run_request(args.run_request_path, run_req)
        result["run_request_path"] = args.run_request_path
        result["profile_name"] = args.profile_name

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
