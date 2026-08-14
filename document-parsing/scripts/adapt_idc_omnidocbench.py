#!/usr/bin/env python3
"""Convert ZIP-only IDC OmniDocBench parse JSON to official prediction Markdown.

This adapter creates a benchmark view from the parser's structured blocks:

* text, title, table, and code blocks keep their original content and order;
* header, footer, and image blocks are omitted because OmniDocBench's official
  end-to-end text score ignores these categories (and removes image links);
* doubly quoted numeric ``rowspan``/``colspan`` values are losslessly
  normalized to valid HTML attributes;
* no OCR text, table, formula, title level, or reading order is repaired.

Prediction filenames are mapped from ``page-123.pdf`` to ``page-123.md`` to
match the image stems in OmniDocBench.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath


SCRIPT_DIR = Path(__file__).resolve().parent
TRACK_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = (
    TRACK_DIR / "runs" / "omnidocbench-idc-4.1.14-vlm-final-1651"
)
DEFAULT_OUTPUT_DIR = (
    TRACK_DIR
    / "runs"
    / "omnidocbench-idc-4.1.14-vlm-final-1651-official-md"
)
DEFAULT_GOLDEN = TRACK_DIR / "datasets" / "omnidocbench" / "OmniDocBench.json"


@dataclass
class Record:
    zip: str
    status: str
    source_member: str | None = None
    output: str | None = None
    output_sha256: str | None = None
    emitted_blocks: int = 0
    omitted_blocks: int = 0
    normalized_table_attributes: int = 0
    block_types: dict[str, int] | None = None
    detail: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--golden",
        type=Path,
        default=DEFAULT_GOLDEN,
        help="OmniDocBench JSON used to validate output names",
    )
    parser.add_argument(
        "--no-golden-validation",
        action="store_true",
        help="do not check converted filenames against OmniDocBench JSON",
    )
    parser.add_argument("--max-files", type=int, help="convert at most N ZIP files")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing Markdown file when its bytes differ",
    )
    return parser.parse_args()


def load_golden_stems(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        samples = json.load(handle)
    stems: set[str] = set()
    for sample in samples:
        image_path = sample.get("page_info", {}).get("image_path")
        if image_path:
            stems.add(Path(image_path).stem)
    if not stems:
        raise ValueError(f"no page_info.image_path entries found in golden: {path}")
    return stems


def find_parse_json(archive: zipfile.ZipFile) -> str:
    candidates = []
    for name in archive.namelist():
        path = PurePosixPath(name)
        if not path.name.endswith("_parse.json") or "debug" in path.parts:
            continue
        candidates.append(name)
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one parse JSON, found {len(candidates)}: "
            + ", ".join(candidates[:5])
        )
    return candidates[0]


def official_name(filename: str) -> str:
    name = PurePosixPath(filename).name
    stem = name
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    if not stem:
        raise ValueError(f"cannot derive official filename from: {filename}")
    return f"{stem}.md"


DOUBLE_QUOTED_NUMERIC_SPAN = re.compile(
    r"\b(rowspan|colspan)='\\\"([1-9]\d*)\\\"'"
)


def normalize_table_attributes(content: str) -> tuple[str, int]:
    """Undo an unambiguous serialization escape in numeric span attributes."""

    return DOUBLE_QUOTED_NUMERIC_SPAN.subn(r'\1="\2"', content)


def render_markdown(
    parse_result: dict,
) -> tuple[str, int, int, int, dict[str, int]]:
    blocks = parse_result.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("parse JSON field 'blocks' must be a list")

    allowed = {"text", "title", "table", "code"}
    omitted = {"header", "footer", "image"}
    parts: list[str] = []
    type_counts: dict[str, int] = {}
    omitted_count = 0
    normalized_attribute_count = 0

    for position, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError(f"block {position} is not an object")
        block_type = block.get("type")
        if not isinstance(block_type, str):
            raise ValueError(f"block {position} has no string type")
        type_counts[block_type] = type_counts.get(block_type, 0) + 1

        if block_type in omitted:
            omitted_count += 1
            continue
        if block_type not in allowed:
            raise ValueError(f"block {position} has unsupported type: {block_type}")

        content = block.get("content")
        if not isinstance(content, str):
            raise ValueError(f"{block_type} block {position} has no string content")
        content = content.strip("\n")
        if not content:
            continue

        if block_type == "table":
            content, normalized = normalize_table_attributes(content)
            normalized_attribute_count += normalized
        elif block_type == "title":
            raw_level = block.get("level")
            try:
                level = int(raw_level)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"title block {position} has invalid level: {raw_level!r}"
                ) from exc
            if not 1 <= level <= 6:
                raise ValueError(
                    f"title block {position} level is outside Markdown range: {level}"
                )
            content = f"{'#' * level} {content}"
        parts.append(content)

    markdown = "\n\n".join(parts)
    if markdown:
        markdown += "\n"
    return (
        markdown,
        len(parts),
        omitted_count,
        normalized_attribute_count,
        type_counts,
    )


def write_prediction(
    output_path: Path, content: bytes, overwrite: bool
) -> tuple[str, str | None]:
    if output_path.exists():
        current = output_path.read_bytes()
        if current == content:
            return "skipped", "identical output already exists"
        if not overwrite:
            raise FileExistsError(
                f"different output already exists: {output_path}; use --overwrite"
            )
    output_path.write_bytes(content)
    return "converted", None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def portable_path(path: Path | None) -> str | None:
    """Prefer a repository-relative path in the persisted adapter manifest."""

    if path is None:
        return None
    try:
        return path.relative_to(TRACK_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    golden = None if args.no_golden_validation else args.golden.resolve()

    if not input_dir.is_dir():
        print(f"error: input directory does not exist: {input_dir}", file=sys.stderr)
        return 2
    if golden is not None and not golden.is_file():
        print(f"error: golden file does not exist: {golden}", file=sys.stderr)
        return 2

    golden_stems = load_golden_stems(golden)
    archives = sorted(input_dir.glob("*.zip"), key=lambda path: path.name)
    if args.max_files is not None:
        if args.max_files < 0:
            print("error: --max-files must be non-negative", file=sys.stderr)
            return 2
        archives = archives[: args.max_files]
    output_dir.mkdir(parents=True, exist_ok=True)

    records: list[Record] = []
    for index, archive_path in enumerate(archives, 1):
        try:
            with zipfile.ZipFile(archive_path) as archive:
                member = find_parse_json(archive)
                parse_result = json.loads(archive.read(member))
                filename = parse_result.get("filename")
                if not isinstance(filename, str) or not filename:
                    raise ValueError("parse JSON has no non-empty string filename")
                output_name = official_name(filename)
                if golden_stems is not None and Path(output_name).stem not in golden_stems:
                    raise ValueError(f"output name is absent from golden: {output_name}")
                markdown, emitted, omitted, normalized, type_counts = render_markdown(
                    parse_result
                )
                content = markdown.encode("utf-8")
            status, detail = write_prediction(
                output_dir / output_name, content, args.overwrite
            )
            record = Record(
                zip=archive_path.name,
                status=status,
                source_member=member,
                output=output_name,
                output_sha256=sha256_bytes(content),
                emitted_blocks=emitted,
                omitted_blocks=omitted,
                normalized_table_attributes=normalized,
                block_types=type_counts,
                detail=detail,
            )
            print(f"[{index}/{len(archives)}] {status}: {archive_path.name} -> {output_name}")
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            record = Record(zip=archive_path.name, status="failed", detail=str(exc))
            print(f"[{index}/{len(archives)}] failed: {archive_path.name}: {exc}")
        records.append(record)

    counts = {
        status: sum(record.status == status for record in records)
        for status in ("converted", "skipped", "failed")
    }
    report = {
        "manifest_version": 1,
        "input_dir": portable_path(input_dir),
        "output_dir": portable_path(output_dir),
        "golden": portable_path(golden),
        "golden_sha256": (
            hashlib.sha256(golden.read_bytes()).hexdigest() if golden else None
        ),
        "zip_count": len(archives),
        "counts": counts,
        "output_count": sum(record.output is not None for record in records),
        "empty_output_count": sum(
            record.output is not None
            and (output_dir / record.output).is_file()
            and (output_dir / record.output).stat().st_size == 0
            for record in records
        ),
        "records": [asdict(record) for record in records],
    }
    report_path = output_dir / "adapter-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Summary: total={len(records)} converted={counts['converted']} "
        f"skipped={counts['skipped']} failed={counts['failed']}"
    )
    print(f"Report: {report_path}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
