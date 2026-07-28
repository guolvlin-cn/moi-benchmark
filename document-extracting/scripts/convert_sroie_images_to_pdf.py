#!/usr/bin/env python3
"""Convert the frozen SROIE JPG cases to one-page PDFs."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def convert_image(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid image dimensions: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(
        str(destination),
        pagesize=(float(width), float(height)),
        pageCompression=1,
    )
    pdf.drawImage(
        ImageReader(str(source)),
        0,
        0,
        width=float(width),
        height=float(height),
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("document-extracting/datasets/SROIE2019/train/img"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("document-extracting/datasets/SROIE2019/train/pdf"),
    )
    args = parser.parse_args()

    images = sorted(args.input_dir.glob("*.jpg"))
    if not images:
        raise SystemExit(f"No JPG images found in {args.input_dir}")

    for source in images:
        convert_image(source, args.output_dir / f"{source.stem}.pdf")

    print(f"Converted {len(images)} images to {args.output_dir}")


if __name__ == "__main__":
    main()
