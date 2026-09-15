#!/usr/bin/env python3
"""Create the EXIF-oriented preview that the visual proposer must inspect."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from crop_photo import CropError, load_oriented_image


def prepare_photo(
    source: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> dict:
    """Write a lossless oriented preview and its source metadata."""
    output = Path(output_dir)
    preview_path = output / "source-oriented.png"
    metadata_path = output / "source-metadata.json"
    existing = [path for path in (preview_path, metadata_path) if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise CropError(f"Output already exists: {names}. Use --overwrite to replace it.")

    image, metadata = load_oriented_image(source)
    output.mkdir(parents=True, exist_ok=True)
    icc_profile = metadata.pop("icc_profile")
    save_options = {"format": "PNG"}
    if icc_profile:
        save_options["icc_profile"] = icc_profile
    image.save(preview_path, **save_options)
    metadata["preview_file"] = preview_path.name
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an EXIF-oriented PNG preview for visual crop planning."
    )
    parser.add_argument("source", type=Path, help="JPG, JPEG, PNG, or WebP source")
    parser.add_argument("--output-dir", required=True, type=Path, help="Preview output directory")
    parser.add_argument("--overwrite", action="store_true", help="Replace matching outputs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = prepare_photo(args.source, args.output_dir, overwrite=args.overwrite)
    except CropError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
