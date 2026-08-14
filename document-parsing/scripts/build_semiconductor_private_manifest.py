#!/usr/bin/env python3
"""Build the reproducibility manifest for the 50-file private benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


SCORER_COMMIT = "06faf76112c998835f0f9ca174a5f2d311d559f2"
# Source/Golden page counts recorded in the formal score workbook differ from
# parser-emitted max(page_num) for these two files. Keep the evaluation grouping
# frozen to the source/Golden count rather than parser output.
PAGE_COUNT_OVERRIDES = {
    "112跨页表解析两次.docx": 1,
    "145页眉下的图片被识别为表格一部分.docx": 5,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_id(path: Path, source_dir: Path) -> str:
    relative = path.relative_to(source_dir).as_posix()
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        if file_path.name == ".DS_Store":
            continue
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(file_path)))
        digest.update(b"\0")
    return digest.hexdigest()


def member(archive: zipfile.ZipFile, suffix: str) -> str:
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one *{suffix}, found {len(matches)}")
    return matches[0]


def moi_metadata(zip_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as archive:
        parse_member = member(archive, "_parse.json")
        config_member = member(archive, ".yaml")
        parse_bytes = archive.read(parse_member)
        config_bytes = archive.read(config_member)
        parsed = json.loads(parse_bytes)
        config = yaml.safe_load(config_bytes.decode("utf-8"))
    page_count = max(
        [int(block.get("page_num") or 1) for block in parsed.get("blocks", [])] + [1]
    )
    selected = {
        "vlm_model": config.get("vlm_model"),
        "enable_doc_libreoffice_openxml": bool(
            config.get("enable_doc_libreoffice_openxml", False)
        ),
        "enable_image_fragment_merge": bool(
            config.get("enable_image_fragment_merge", False)
        ),
        "enable_header_footer_as_text": bool(
            config.get("enable_header_footer_as_text", False)
        ),
    }
    group = "vlm={vlm};libreoffice={libreoffice};image_fragment={image_fragment}".format(
        vlm=selected["vlm_model"] or "inherit",
        libreoffice=str(selected["enable_doc_libreoffice_openxml"]).lower(),
        image_fragment=str(selected["enable_image_fragment_merge"]).lower(),
    )
    return {
        "zip_sha256": sha256_file(zip_path),
        "parse_member": parse_member,
        "parse_sha256": sha256_bytes(parse_bytes),
        "parser_config_member": config_member,
        "parser_config_sha256": sha256_bytes(config_bytes),
        "config_group": group,
        "selected_config": selected,
        "parser_page_count": page_count,
    }


def main() -> int:
    base_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-parsing-dir", type=Path, default=base_default)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.document_parsing_dir.resolve()
    source_dir = base / "datasets" / "半导体场景模拟数据"
    golden_dir = base / "datasets" / "半导体场景模拟数据golden"
    runs = base / "runs"
    files = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
    if len(files) != 50:
        parser.error(f"expected 50 source files, found {len(files)}")

    records: list[dict[str, Any]] = []
    groups: Counter[str] = Counter()
    for source in files:
        case_id = stable_id(source, source_dir)
        case_name = f"{source.name}--{case_id}"
        golden = golden_dir / f"{source.name}.json"
        moi_zip = runs / "半导体场景私有数据集-idc-4.1.14" / f"{case_name}.zip"
        mineru_case = runs / "半导体场景模拟数据-mineru-precision" / case_name
        mineru_content = list(mineru_case.glob("*_content_list.json"))
        paddle_case = runs / "半导体场景模拟数据-paddleocr-vl" / case_name
        paths = [source, golden, moi_zip, mineru_case, paddle_case]
        if not all(path.exists() for path in paths) or len(mineru_content) != 1:
            raise FileNotFoundError(f"incomplete case artifacts: {case_name}")

        moi = moi_metadata(moi_zip)
        page_count = PAGE_COUNT_OVERRIDES.get(source.name, moi["parser_page_count"])
        groups[moi["config_group"]] += 1
        golden_data = json.loads(golden.read_text(encoding="utf-8"))
        mineru_converted = (
            runs
            / "半导体场景模拟数据-mineru-precision"
            / "converted_parsed"
            / f"{case_name}_parse.json"
        )
        paddle_converted = (
            runs
            / "半导体场景模拟数据-paddleocr-vl"
            / "converted_parsed"
            / f"{case_name}_parse.json"
        )
        records.append(
            {
                "source_file": relative(source, base),
                "source_sha256": sha256_file(source),
                "case_id": case_id,
                "format": source.suffix.lower().lstrip("."),
                "page_count": page_count,
                "golden_file": relative(golden, base),
                "golden_sha256": sha256_file(golden),
                "golden_doc_id": golden_data.get("doc_id"),
                "golden_reviewed": bool(golden_data.get("_reviewed", False)),
                "moi": {"zip": relative(moi_zip, base), **moi},
                "mineru": {
                    "case_dir": relative(mineru_case, base),
                    "case_tree_sha256": tree_sha256(mineru_case),
                    "content_list": relative(mineru_content[0], base),
                    "content_list_sha256": sha256_file(mineru_content[0]),
                    "converted_parsed": relative(mineru_converted, base),
                    "converted_parsed_sha256": sha256_file(mineru_converted),
                },
                "paddleocr_vl": {
                    "case_dir": relative(paddle_case, base),
                    "case_tree_sha256": tree_sha256(paddle_case),
                    "result_json": relative(paddle_case / "result.json", base),
                    "result_json_sha256": sha256_file(paddle_case / "result.json"),
                    "converted_parsed": relative(paddle_converted, base),
                    "converted_parsed_sha256": sha256_file(paddle_converted),
                },
            }
        )

    report_files = [
        base / "evaluate" / "半导体场景私有数据集评测报告.md",
        base / "evaluate" / "idc-4.1.14_半导体场景模拟数据_解析benchmark评分.xlsx",
        base / "evaluate" / "mineru_半导体场景模拟数据_解析benchmark评分.xlsx",
        base / "evaluate" / "paddleocr-vl_半导体场景模拟数据_解析benchmark评分.xlsx",
        base / "evaluate" / "semiconductor-private-final" / "reproduced-score.json",
    ]
    payload = {
        "schema_version": "semiconductor-private-manifest-v1",
        "dataset": "半导体场景模拟数据",
        "case_count": len(records),
        "scorer": {
            "repository": "git@github.com:matrixorigin/moi-parse-bench.git",
            "commit": SCORER_COMMIT,
            "package": "moi-parsing-benchmark",
            "package_version": "1.0.0",
        },
        "moi_config_group_counts": dict(sorted(groups.items())),
        "golden_review": {
            "reviewed": sum(record["golden_reviewed"] for record in records),
            "draft": sum(not record["golden_reviewed"] for record in records),
        },
        "report_artifacts": {
            relative(path, base): sha256_file(path)
            for path in report_files
            if path.is_file()
        },
        "cases": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} ({len(records)} cases)")
    print(f"config groups: {dict(sorted(groups.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
