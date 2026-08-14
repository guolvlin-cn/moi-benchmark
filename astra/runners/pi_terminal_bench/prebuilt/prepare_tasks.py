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
        description="Create isolated task copies using Pi prebuilt images"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--image-prefix", default="moi/pi-tbench")
    parser.add_argument("--image-tag", default="0.73.1")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("tasks", nargs="+")
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
    destination_root.mkdir(parents=True, exist_ok=True)
    for task_name in dict.fromkeys(args.tasks):
        if not TASK_NAME_PATTERN.fullmatch(task_name):
            raise ValueError(f"invalid task name: {task_name}")
        source = source_root / task_name
        destination = destination_root / task_name
        config_path = source / "task.toml"
        config = config_path.read_text(encoding="utf-8")
        if len(DOCKER_IMAGE_PATTERN.findall(config)) != 1:
            raise RuntimeError(f"expected one docker_image in {config_path}")
        image = f"{args.image_prefix}-{task_name}:{args.image_tag}"
        if destination.exists():
            if not args.overwrite:
                raise FileExistsError(f"destination exists: {destination}")
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        (destination / "task.toml").write_text(
            DOCKER_IMAGE_PATTERN.sub(
                f'docker_image = "{image}"', config, count=1
            ),
            encoding="utf-8",
        )
        print(f"{task_name}: {image}")


if __name__ == "__main__":
    main()

