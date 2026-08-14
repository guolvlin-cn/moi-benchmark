from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


CONTAINER_DUMPS = Path("/workspace/dumps")
CONTAINER_WORKSPACE = CONTAINER_DUMPS / "workspace"
MOUNT = "/usr/bin/mount"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir() or workspace.is_symlink():
        raise SystemExit("Pi workspace must be a real directory")
    if workspace.name != "workspace" or not workspace.parent.is_dir():
        raise SystemExit("Pi workspace has an unexpected layout")
    if not CONTAINER_DUMPS.is_dir() or CONTAINER_DUMPS.is_symlink():
        raise SystemExit(f"namespace mountpoint is unavailable: {CONTAINER_DUMPS}")
    if not args.command:
        raise SystemExit("Pi command is required")

    subprocess.run(
        [MOUNT, "--bind", str(workspace.parent), str(CONTAINER_DUMPS)],
        check=True,
    )
    if not CONTAINER_WORKSPACE.samefile(workspace):
        raise SystemExit("Pi workspace bind mount identity mismatch")
    os.chdir(CONTAINER_WORKSPACE)
    os.execvpe(args.command[0], args.command, os.environ)


if __name__ == "__main__":
    main()
