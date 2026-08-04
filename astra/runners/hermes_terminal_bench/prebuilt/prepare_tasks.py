#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


TASK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
DOCKER_IMAGE_PATTERN = re.compile(
    r'^[ \t]*docker_image[ \t]*=[ \t]*"([^"]+)"[ \t]*$',
    re.MULTILINE,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create isolated task copies using Hermes prebuilt images"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--image-prefix",
        default="moi/hermes-tbench",
    )
    parser.add_argument("--image-tag", default="v2026.7.20")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace matching managed task directories",
    )
    parser.add_argument(
        "tasks",
        nargs="+",
        metavar="TASK",
        help="one or more task names to copy",
    )
    args = parser.parse_args()

    source_root = args.source.expanduser().resolve()
    destination_root = args.destination.expanduser().resolve()
    if (
        source_root == destination_root
        or source_root.is_relative_to(destination_root)
        or destination_root.is_relative_to(source_root)
    ):
        raise ValueError(
            "source and destination must be separate, non-nested directories"
        )

    tasks = list(dict.fromkeys(args.tasks))
    for task_name in tasks:
        if not TASK_NAME_PATTERN.fullmatch(task_name):
            raise ValueError(f"invalid task name: {task_name}")

    destination_root.mkdir(parents=True, exist_ok=True)
    for task_name in tasks:
        source = source_root / task_name
        destination = destination_root / task_name
        if not (source / "task.toml").is_file():
            raise FileNotFoundError(f"invalid task source: {source}")
        config = (source / "task.toml").read_text(encoding="utf-8")
        if len(DOCKER_IMAGE_PATTERN.findall(config)) != 1:
            raise RuntimeError(
                f"expected one docker_image entry in {source / 'task.toml'}"
            )
        image = f"{args.image_prefix}-{task_name}:{args.image_tag}"
        if destination.exists():
            if not args.overwrite:
                raise FileExistsError(
                    f"destination exists: {destination}; "
                    "pass --overwrite to replace generated copies"
                )
            existing_config_path = destination / "task.toml"
            existing_images = (
                DOCKER_IMAGE_PATTERN.findall(
                    existing_config_path.read_text(encoding="utf-8")
                )
                if existing_config_path.is_file()
                else []
            )
            if existing_images != [image]:
                raise RuntimeError(
                    f"refusing to overwrite unmanaged destination: {destination}"
                )
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

        config_path = destination / "task.toml"
        updated = DOCKER_IMAGE_PATTERN.sub(
            f'docker_image = "{image}"',
            config,
            count=1,
        )
        config_path.write_text(updated, encoding="utf-8")
        print(f"{task_name}: {image}")


if __name__ == "__main__":
    main()
