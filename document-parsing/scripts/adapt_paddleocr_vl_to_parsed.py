#!/usr/bin/env python3
"""Convert Baidu PaddleOCR-VL result.json files to parsing_benchmark JSON.

The mapping is the one used for the semiconductor private-dataset evaluation.
It deliberately maps only fields returned by the API and does not infer missing
captions, OCR text, image paths, or title levels beyond Paddle's explicit type.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence


_HASH_SUFFIX_RE = re.compile(r"--[0-9a-fA-F]{8,}$")


def _string(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _page_num(page: dict[str, Any]) -> int:
    try:
        return max(1, int(page.get("page_num")) + 1)
    except (TypeError, ValueError):
        return 1


def _case_name(path: Path) -> str:
    base = path.parent.name if path.name == "result.json" else path.name
    return _HASH_SUFFIX_RE.sub("", base)


def _bbox(position: Any) -> list[float] | None:
    if not isinstance(position, list) or len(position) != 4:
        return None
    try:
        x, y, width, height = (float(value) for value in position)
    except (TypeError, ValueError):
        return None
    return [x, y, x + width, y + height]


def _title_level(sub_type: str) -> int | None:
    match = re.search(r"title[_-]?(\d+)", sub_type, re.IGNORECASE)
    if not match:
        return None
    level = int(match.group(1))
    return level if level > 0 else None


def _block(layout: dict[str, Any], page_num: int, index: int) -> dict[str, Any]:
    original_type = _string(layout.get("type")).strip().lower() or "text"
    sub_type = _string(layout.get("sub_type")).strip()
    text = _string(layout.get("text"))
    block_id = _string(layout.get("layout_id") or layout.get("id")).strip()
    block_id = block_id or f"paddle-{page_num:04d}-{index:06d}-{uuid.uuid4().hex[:8]}"
    meta: dict[str, Any] = {
        "source": "paddleocr_vl",
        "paddle_type": original_type,
    }
    if sub_type:
        meta["sub_type"] = sub_type
    bbox = _bbox(layout.get("position"))
    if bbox:
        meta["bbox"] = bbox
    if layout.get("polygon") is not None:
        meta["polygon"] = layout.get("polygon")

    def base(block_type: str, content: str = text) -> dict[str, Any]:
        return {
            "id": block_id,
            "index": index,
            "type": block_type,
            "level": None,
            "content": content,
            "page_num": page_num,
            "meta": meta,
        }

    if original_type in {"header", "footer"}:
        return base(original_type)
    if original_type in {"doc_title", "paragraph_title"}:
        result = base("title")
        result["level"] = str(_title_level(sub_type) or 1)
        return result
    if original_type == "table":
        return base("table", _string(layout.get("table_html") or text))
    if original_type in {"image", "chart", "header_image", "footer_image"}:
        return {
            "id": block_id,
            "index": index,
            "type": "image",
            "ocr": text if original_type == "chart" else "",
            "caption": "",
            "image_url": "",
            "page_num": page_num,
            "meta": meta,
        }
    return base("text")


def convert(data: dict[str, Any], input_path: Path) -> dict[str, Any]:
    pages = data.get("pages")
    if not isinstance(pages, list):
        raise ValueError("PaddleOCR-VL result must contain a list field: pages")
    blocks: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_num = _page_num(page)
        layouts = page.get("layouts") or []
        if not isinstance(layouts, list):
            continue
        for layout in layouts:
            if isinstance(layout, dict):
                blocks.append(_block(layout, page_num, len(blocks)))

    filename = _string(data.get("file_name")).strip() or _case_name(input_path)
    filetype = Path(filename).suffix.upper().lstrip(".") or "PDF"
    return {
        "filename": filename,
        "filetype": filetype,
        "block_count": len(blocks),
        "blocks": blocks,
    }


def _inputs(path: Path) -> list[Path]:
    return [path] if path.is_file() else sorted(path.glob("*/result.json"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if not args.input.exists():
        parser.error(f"input does not exist: {args.input}")
    inputs = _inputs(args.input)
    if not inputs:
        parser.error(f"no result.json files found under: {args.input}")

    failures: list[str] = []
    for input_path in inputs:
        output_path = (
            args.output
            if args.input.is_file()
            else args.output / f"{input_path.parent.name}_parse.json"
        )
        if output_path.exists() and not args.force:
            failures.append(f"output exists: {output_path}")
            continue
        try:
            raw = json.loads(input_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON must be an object")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(convert(raw, input_path), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (json.JSONDecodeError, ValueError) as exc:
            failures.append(f"{input_path}: {exc}")

    print(f"converted={len(inputs) - len(failures)} failed={len(failures)}")
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
