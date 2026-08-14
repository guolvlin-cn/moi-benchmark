from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind a Pi batch to the current Toolathlon application credentials"
    )
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.resolve()
    source_root = args.source.resolve()
    output = args.output.resolve()
    record = json.loads(base.read_text(encoding="utf-8"))
    application = record.get("toolathlon_application_credentials")
    files = application.get("files") if isinstance(application, dict) else None
    if record.get("secret_values_recorded") is not False or not isinstance(files, list):
        raise SystemExit("base credential manifest is not a redacted application manifest")

    for item in files:
        if not isinstance(item, dict):
            raise SystemExit("invalid application credential record")
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise SystemExit(f"unsafe credential path: {relative}")
        path = source_root / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"credential file is unavailable: {path}")
        item["mode"] = oct(stat.S_IMODE(path.stat().st_mode))
        item["size_bytes"] = path.stat().st_size
        item["sha256"] = sha256_file(path)

    canonical = json.dumps(
        files,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    application["root_sha256"] = hashlib.sha256(canonical).hexdigest()
    record["frozen_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record["runtime_rebaseline"] = {
        "base_manifest_sha256": sha256_file(base),
        "reason": "bind a reproducibility batch to the deployed application identities",
        "scope": "application credential file fingerprints only",
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
