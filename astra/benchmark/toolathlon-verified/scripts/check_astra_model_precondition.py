#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from astra.runners.toolathlon_verified.adapter_common import (
    EphemeralState,
    write_astra_credentials,
)
from astra.runners.toolathlon_verified.astra_adapter import AstraRuntime, _run_admin


def main() -> int:
    token = os.environ.get("ASTRA_ADMIN_ACCESS_TOKEN", "")
    if not token:
        print("Astra admin token is unavailable", file=sys.stderr)
        return 1
    runtime = AstraRuntime.load(
        REPO_ROOT / "astra/work/toolathlon-verified/rendered-astra-runtime.json"
    )
    with EphemeralState(prefix="toolathlon-astra-model-preflight-") as state:
        home = state.path / "home"
        home.mkdir(mode=0o700)
        credentials = state.path / "admin-credentials"
        write_astra_credentials(credentials, token)
        result = _run_admin(
            runtime,
            credentials,
            ["model", "show", "deepseek-v4-flash"],
            home=home,
        )
    if result.returncode != 0:
        print(
            "Astra deepseek-v4-flash is not pre-provisioned; refusing scored runs",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "GO",
                "model": "deepseek-v4-flash",
                "check": "admin_model_show_only",
                "provider_request_expected": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
