#!/usr/bin/env python3
"""Resolve Toolathlon image tags to linux/amd64 registry manifest digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_without_tag(reference: str) -> str:
    final_component = reference.rsplit("/", 1)[-1]
    if ":" not in final_component:
        return reference
    return reference.rsplit(":", 1)[0]


def inspect(reference: str) -> dict[str, Any]:
    command = [
        "skopeo",
        "inspect",
        "--override-os",
        "linux",
        "--override-arch",
        "amd64",
        f"docker://{reference}",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        return {
            "reference": reference,
            "state": "NO_GO",
            "error": result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "inspect failed",
        }
    data = json.loads(result.stdout)
    digest = data.get("Digest")
    return {
        "reference": reference,
        "state": "frozen",
        "platform": {"os": data.get("Os"), "architecture": data.get("Architecture")},
        "manifest_digest": digest,
        "immutable_reference": f"{repository_without_tag(reference)}@{digest}",
        "created": data.get("Created"),
        "layer_count": len(data.get("Layers", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-dir", type=Path, required=True)
    args = parser.parse_args()

    freeze_dir = args.freeze_dir.resolve()
    section_path = freeze_dir / "section-3.2.freeze.json"
    section = json.loads(section_path.read_text(encoding="utf-8"))
    references = [section["task_image"]["tag_reference"]]
    references.extend(section["auxiliary_images"]["declared_references"])

    previous_path = freeze_dir / "image-manifest.json"
    previous_records: dict[str, dict[str, Any]] = {}
    if previous_path.is_file():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        previous_records = {
            record["reference"]: record
            for record in previous.get("images", [])
            if record.get("state") == "frozen"
        }

    records: list[dict[str, Any]] = []
    for position, reference in enumerate(references, start=1):
        if reference in previous_records:
            print(f"[{position}/{len(references)}] cached {reference}", flush=True)
            records.append(previous_records[reference])
        else:
            print(f"[{position}/{len(references)}] resolve {reference}", flush=True)
            records.append(inspect(reference))

    unresolved = [record for record in records if record["state"] != "frozen"]
    payload = {
        "schema_version": 1,
        "source_commit": "2aed2468858f15818acafa178518390cc4b0f5cb",
        "frozen_at": section["frozen_at"],
        "platform": {"os": "linux", "architecture": "amd64"},
        "state": "frozen" if not unresolved else "NO_GO",
        "resolved_count": len(records) - len(unresolved),
        "unresolved_count": len(unresolved),
        "images": records,
        "local_task_image_archive": section["task_image"].get("local_oci_archive"),
    }
    output = freeze_dir / "image-manifest.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    image_manifest_sha256 = sha256_file(output)

    auxiliary = section["auxiliary_images"]
    auxiliary["state"] = payload["state"]
    auxiliary["resolved_count"] = payload["resolved_count"] - 1
    auxiliary["unresolved_count"] = payload["unresolved_count"]
    auxiliary["image_manifest"] = {
        "path": output.name,
        "sha256": image_manifest_sha256,
    }
    if unresolved:
        auxiliary["reason"] = "one or more required image references could not be resolved"
    else:
        auxiliary.pop("reason", None)
    task_record = records[0]
    section["task_image"]["registry_digest_verified"] = (
        task_record.get("manifest_digest") == section["task_image"]["manifest_digest"]
    )
    section_path.write_text(
        json.dumps(section, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    aggregate_path = freeze_dir / "sections-3.1-3.2.sha256"
    aggregate_files = sorted(
        path for path in freeze_dir.iterdir() if path.is_file() and path != aggregate_path
    )
    aggregate_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in aggregate_files),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": image_manifest_sha256,
                "resolved": payload["resolved_count"],
                "unresolved": payload["unresolved_count"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
