#!/usr/bin/env python3
"""Destructively retain the frozen 100-case subset for each extraction dataset."""

from __future__ import annotations

import hashlib
import json
import lzma
import random
import shutil
from pathlib import Path


SEED = 20260723
ROOT = Path(__file__).resolve().parents[1] / "datasets"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(dataset_root: Path, dataset: str, strategy: str, cases: list[dict]) -> None:
    payload = {
        "dataset": dataset,
        "selection_strategy": strategy,
        "seed": SEED,
        "case_count": len(cases),
        "cases": cases,
    }
    (dataset_root / "selection_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def select_sroie() -> None:
    root = ROOT / "SROIE2019"
    train = root / "train"
    stems_by_kind = {
        kind: {path.stem for path in (train / kind).iterdir() if path.is_file()}
        for kind in ("img", "box", "entities")
    }
    candidates = sorted(set.intersection(*stems_by_kind.values()))
    if len(candidates) < 100:
        raise RuntimeError(f"SROIE has only {len(candidates)} complete train cases")

    selected = sorted(random.Random(SEED).sample(candidates, 100))
    selected_set = set(selected)
    cases = []
    for stem in selected:
        image = next(path for path in (train / "img").iterdir() if path.is_file() and path.stem == stem)
        box = next(path for path in (train / "box").iterdir() if path.is_file() and path.stem == stem)
        entities = next(
            path for path in (train / "entities").iterdir() if path.is_file() and path.stem == stem
        )
        cases.append(
            {
                "case_id": stem,
                "split": "train",
                "image": str(image.relative_to(root)),
                "box": str(box.relative_to(root)),
                "entities": str(entities.relative_to(root)),
                "image_sha256": sha256(image),
            }
        )

    for kind in ("img", "box", "entities"):
        for path in (train / kind).iterdir():
            if path.is_file() and path.stem not in selected_set:
                path.unlink()

    for removable in (root / "test", root / "layoutlm-base-uncased"):
        if removable.exists():
            shutil.rmtree(removable)

    write_manifest(
        root,
        "SROIE2019",
        "100 complete cases sampled from train with Python random.Random(seed).sample over sorted IDs",
        cases,
    )


def select_vrdu() -> None:
    root = ROOT / "VRDU"
    registration = root / "registration-form"
    main = registration / "main"
    split_name = "FARA-lv2-mixed_template-train_10-test_300-valid_100-SD_0.json"
    split_path = registration / "few_shot-splits" / split_name
    split = json.loads(split_path.read_text(encoding="utf-8"))
    selected = list(split["valid"])
    if len(selected) != 100 or len(set(selected)) != 100:
        raise RuntimeError("VRDU official valid split is not 100 unique cases")
    selected_set = set(selected)

    dataset_path = main / "dataset.jsonl"
    retained_rows = []
    with dataset_path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["filename"] in selected_set:
                retained_rows.append(row)
    found = {row["filename"] for row in retained_rows}
    if found != selected_set:
        raise RuntimeError(f"VRDU missing annotations: {sorted(selected_set - found)}")

    pdf_dir = main / "pdfs"
    pdf_names = {path.name for path in pdf_dir.glob("*.pdf")}
    if not selected_set <= pdf_names:
        raise RuntimeError(f"VRDU missing PDFs: {sorted(selected_set - pdf_names)}")

    for path in pdf_dir.glob("*.pdf"):
        if path.name not in selected_set:
            path.unlink()
    with dataset_path.open("w", encoding="utf-8") as handle:
        for row in retained_rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    gz_path = main / "dataset.jsonl.gz"
    if gz_path.exists():
        gz_path.unlink()
    for path in (registration / "few_shot-splits").glob("*.json"):
        if path.name != split_name:
            path.unlink()
    for removable in (root / "ad-buy-form", root / ".git"):
        if removable.exists():
            shutil.rmtree(removable)

    cases = [
        {
            "case_id": Path(filename).stem,
            "split": "valid",
            "pdf": f"registration-form/main/pdfs/{filename}",
            "pdf_sha256": sha256(pdf_dir / filename),
        }
        for filename in selected
    ]
    write_manifest(
        root,
        "VRDU Registration",
        f"official valid list from registration-form/few_shot-splits/{split_name}",
        cases,
    )


def read_xz_lines(path: Path) -> list[str]:
    with lzma.open(path, "rt", encoding="utf-8") as handle:
        return handle.readlines()


def write_xz_lines(path: Path, lines: list[str]) -> None:
    with lzma.open(path, "wt", encoding="utf-8") as handle:
        handle.writelines(lines)


def select_kleister() -> None:
    root = ROOT / "Kleister-NDA"
    dev_in = read_xz_lines(root / "dev-0" / "in.tsv.xz")
    train_in = read_xz_lines(root / "train" / "in.tsv.xz")
    dev_expected = (root / "dev-0" / "expected.tsv").read_text(encoding="utf-8").splitlines(True)
    train_expected = (root / "train" / "expected.tsv").read_text(encoding="utf-8").splitlines(True)
    train_expected_original_path = root / "train" / "expected-original.tsv"
    train_expected_original = train_expected_original_path.read_text(encoding="utf-8").splitlines(True)

    if len(dev_in) != 83 or len(dev_expected) != 83:
        raise RuntimeError("Kleister dev-0 no longer contains the expected 83 aligned cases")
    if not (len(train_in) == len(train_expected) == len(train_expected_original)):
        raise RuntimeError("Kleister train input and expected files are not aligned")

    train_indices = sorted(random.Random(SEED).sample(range(len(train_in)), 17))
    selected_train_in = [train_in[index] for index in train_indices]
    selected_train_expected = [train_expected[index] for index in train_indices]
    selected_train_original = [train_expected_original[index] for index in train_indices]

    write_xz_lines(root / "train" / "in.tsv.xz", selected_train_in)
    (root / "train" / "expected.tsv").write_text("".join(selected_train_expected), encoding="utf-8")
    train_expected_original_path.write_text("".join(selected_train_original), encoding="utf-8")

    selected_rows = [("dev-0", row) for row in dev_in] + [
        ("train", row) for row in selected_train_in
    ]
    selected_pdfs = [row.split("\t", 1)[0] for _, row in selected_rows]
    if len(selected_pdfs) != 100 or len(set(selected_pdfs)) != 100:
        raise RuntimeError("Kleister selection is not 100 unique PDFs")
    selected_set = set(selected_pdfs)

    documents = root / "documents"
    existing = {path.name for path in documents.glob("*.pdf")}
    if not selected_set <= existing:
        raise RuntimeError(f"Kleister missing PDFs: {sorted(selected_set - existing)}")
    for path in documents.glob("*.pdf"):
        if path.name not in selected_set:
            path.unlink()
    for removable in (root / "test-A", root / ".git"):
        if removable.exists():
            shutil.rmtree(removable)

    cases = [
        {
            "case_id": Path(filename).stem,
            "split": split,
            "pdf": f"documents/{filename}",
            "pdf_sha256": sha256(documents / filename),
        }
        for (split, _), filename in zip(selected_rows, selected_pdfs)
    ]
    write_manifest(
        root,
        "Kleister-NDA",
        "all 83 dev-0 cases plus 17 train cases sampled with Python random.Random(seed).sample",
        cases,
    )


def verify() -> None:
    sroie = ROOT / "SROIE2019"
    for kind in ("img", "box", "entities"):
        count = len([path for path in (sroie / "train" / kind).iterdir() if path.is_file()])
        if count != 100:
            raise RuntimeError(f"SROIE {kind} count is {count}, expected 100")

    vrdu = ROOT / "VRDU"
    if len(list((vrdu / "registration-form" / "main" / "pdfs").glob("*.pdf"))) != 100:
        raise RuntimeError("VRDU PDF count is not 100")
    with (vrdu / "registration-form" / "main" / "dataset.jsonl").open(encoding="utf-8") as handle:
        if sum(1 for _ in handle) != 100:
            raise RuntimeError("VRDU annotation row count is not 100")

    kleister = ROOT / "Kleister-NDA"
    if len(list((kleister / "documents").glob("*.pdf"))) != 100:
        raise RuntimeError("Kleister PDF count is not 100")
    if len(read_xz_lines(kleister / "dev-0" / "in.tsv.xz")) != 83:
        raise RuntimeError("Kleister dev-0 count is not 83")
    if len(read_xz_lines(kleister / "train" / "in.tsv.xz")) != 17:
        raise RuntimeError("Kleister train count is not 17")


def main() -> None:
    select_sroie()
    select_vrdu()
    select_kleister()
    verify()
    print("Selection complete: SROIE=100, VRDU Registration=100, Kleister-NDA=100")


if __name__ == "__main__":
    main()
