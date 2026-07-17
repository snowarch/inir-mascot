#!/usr/bin/env python3
"""Validate the canonical Kira art repository and an optional release pack.

The repository contains a small amount of published legacy art that predates
current optimization rules. Those files remain additive-compatible and are
reported as warnings. New or changed art is held to the current contract:
semantic filenames, max 640 px, PNG8 for static cutouts, transparency outside
known editorial pieces, and multi-frame GIFs for animations.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Iterable

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSET_RE = re.compile(r"^inir-mascot-([a-z0-9]+(?:-[a-z0-9]+)*)\.(png|gif)$")
CATALOG_RE = re.compile(r'src="\./(inir-mascot-[^"]+\.(?:png|gif))"')
STREET_TABLE_RE = re.compile(r"^\|\s*(street-[a-z0-9-]+)\s*\|", re.MULTILINE)
EDITORIAL_POSES = {
    "base",
    "expression-sheet",
    "hero-banner",
    "street-smoke-den",
    "street-scheme-station",
}


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
    ).strip()


def asset_paths() -> list[Path]:
    return sorted(
        path
        for path in ROOT.iterdir()
        if path.is_file() and ASSET_RE.fullmatch(path.name)
    )


def pose_name(path: Path) -> str:
    match = ASSET_RE.fullmatch(path.name)
    if not match:
        raise ValueError(f"invalid mascot asset name: {path.name}")
    return match.group(1)


def working_tree_asset_changes() -> set[str]:
    changed: set[str] = set()
    output = git_output("status", "--porcelain=v1", "--untracked-files=all")
    for line in output.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:]
        names = raw.split(" -> ") if " -> " in raw else [raw]
        for name in names:
            if ASSET_RE.fullmatch(Path(name).name):
                changed.add(Path(name).name)
    return changed


def release_asset_changes() -> tuple[set[str], str]:
    tags = git_output("tag", "--sort=-version:refname").splitlines()
    if not tags:
        return {path.name for path in asset_paths()}, "repository start"
    base = tags[0]
    changed = {
        Path(name).name
        for name in git_output("diff", "--name-only", f"{base}..HEAD").splitlines()
        if ASSET_RE.fullmatch(Path(name).name)
    }
    return changed, base


def quality_issues(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    pose = pose_name(path)
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                errors.append("empty dimensions")
            if max(width, height) > 640:
                errors.append(f"{width}x{height} exceeds 640 px")

            if path.suffix == ".png":
                if image.format != "PNG":
                    errors.append(f"extension is PNG but format is {image.format}")
                if image.mode != "P":
                    errors.append(f"mode {image.mode}, expected optimized PNG8 palette")
                else:
                    colors = image.getcolors(maxcolors=256)
                    if colors is None or len(colors) > 255:
                        errors.append("palette exceeds the 255-color shipping limit")

                rgba = image.convert("RGBA")
                alpha = rgba.getchannel("A")
                minimum_alpha, maximum_alpha = alpha.getextrema()
                if maximum_alpha == 0:
                    errors.append("image is fully transparent")
                if pose not in EDITORIAL_POSES and minimum_alpha == 255:
                    errors.append("cutout has no transparent pixels")

                corners = (
                    rgba.getpixel((0, 0))[3],
                    rgba.getpixel((width - 1, 0))[3],
                    rgba.getpixel((0, height - 1))[3],
                    rgba.getpixel((width - 1, height - 1))[3],
                )
                if pose not in EDITORIAL_POSES and any(value > 0 for value in corners):
                    notes.append(f"content touches a crop corner: {corners}")
            else:
                if image.format != "GIF":
                    errors.append(f"extension is GIF but format is {image.format}")
                frames = int(getattr(image, "n_frames", 1))
                if frames < 2:
                    errors.append("animation contains fewer than two frames")
    except (OSError, ValueError) as exc:
        errors.append(f"cannot decode image: {exc}")
    return errors, notes


def validate_catalog(assets: Iterable[Path], errors: list[str]) -> None:
    catalog_path = ROOT / "CATALOG.md"
    if not catalog_path.exists():
        errors.append("CATALOG.md is missing")
        return
    references = CATALOG_RE.findall(catalog_path.read_text(encoding="utf-8"))
    asset_names = {path.name for path in assets}
    reference_names = set(references)
    missing = sorted(asset_names - reference_names)
    stale = sorted(reference_names - asset_names)
    duplicates = sorted({name for name in references if references.count(name) > 1})
    if missing:
        errors.append("CATALOG.md misses: " + ", ".join(missing))
    if stale:
        errors.append("CATALOG.md references missing files: " + ", ".join(stale))
    if duplicates:
        errors.append("CATALOG.md duplicates: " + ", ".join(duplicates))


def validate_street_docs(assets: Iterable[Path], errors: list[str]) -> None:
    street_path = ROOT / "STREET.md"
    if not street_path.exists():
        errors.append("STREET.md is missing")
        return
    text = street_path.read_text(encoding="utf-8")
    street_poses = {
        pose_name(path) for path in assets if pose_name(path).startswith("street-")
    }
    undocumented = sorted(
        pose
        for pose in street_poses
        if pose not in text and pose.removeprefix("street-") not in text
    )
    table_poses = set(STREET_TABLE_RE.findall(text))
    stale_rows = sorted(pose for pose in table_poses if pose not in street_poses)
    if undocumented:
        errors.append("street assets missing from STREET.md: " + ", ".join(undocumented))
    if stale_rows:
        errors.append("STREET.md table rows without assets: " + ", ".join(stale_rows))


def validate_pack(pack_path: Path, assets: Iterable[Path], errors: list[str]) -> None:
    if not pack_path.exists():
        errors.append(f"pack does not exist: {pack_path}")
        return
    expected = {path.name for path in assets}
    try:
        with tarfile.open(pack_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            unsafe = sorted(
                name
                for name in names
                if Path(name).is_absolute() or ".." in Path(name).parts
            )
            nested = sorted(name for name in names if Path(name).parent != Path("."))
            actual = {name for name in names if ASSET_RE.fullmatch(name)}
            extras = sorted(set(names) - actual)
            missing = sorted(expected - actual)
            stale = sorted(actual - expected)
            if unsafe:
                errors.append("pack contains unsafe paths: " + ", ".join(unsafe))
            if nested:
                errors.append("pack contains nested paths: " + ", ".join(nested))
            if extras:
                errors.append("pack contains non-runtime files: " + ", ".join(extras))
            if missing:
                errors.append("pack misses assets: " + ", ".join(missing))
            if stale:
                errors.append("pack contains stale assets: " + ", ".join(stale))
    except (OSError, tarfile.TarError) as exc:
        errors.append(f"cannot inspect pack: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--release",
        action="store_true",
        help="validate every asset changed since the latest release tag",
    )
    parser.add_argument(
        "--pack",
        type=Path,
        help="also verify an installable tar.gz against the canonical assets",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print every legacy warning instead of only the warning count",
    )
    args = parser.parse_args()

    assets = asset_paths()
    errors: list[str] = []
    warnings: list[str] = []
    if not assets:
        errors.append("no mascot assets found")

    stems: dict[str, list[str]] = {}
    for path in assets:
        match = ASSET_RE.fullmatch(path.name)
        if not match:
            errors.append(f"invalid filename: {path.name}")
            continue
        stems.setdefault(match.group(1), []).append(path.name)
    for stem, names in sorted(stems.items()):
        if len(names) > 1:
            errors.append(f"pose has multiple runtime files ({stem}): {', '.join(names)}")

    if args.release:
        quality_targets, baseline = release_asset_changes()
        mode = f"release delta since {baseline}"
    else:
        quality_targets = working_tree_asset_changes()
        mode = "working-tree delta"

    for path in assets:
        image_errors, image_notes = quality_issues(path)
        enforce = path.name in quality_targets
        for issue in image_errors:
            message = f"{path.name}: {issue}"
            (errors if enforce else warnings).append(message)
        for note in image_notes:
            warnings.append(f"{path.name}: {note}")

    validate_catalog(assets, errors)
    validate_street_docs(assets, errors)
    if args.pack:
        pack_path = args.pack if args.pack.is_absolute() else ROOT / args.pack
        validate_pack(pack_path, assets, errors)

    print(f"assets: {len(assets)}")
    print(f"quality scope: {mode} ({len(quality_targets)} asset(s))")
    if warnings:
        print(f"warnings: {len(warnings)}")
        if args.verbose:
            for warning in warnings:
                print(f"  warning: {warning}")
        else:
            print("  run 'python3 scripts/validate.py --verbose' for details")
    if errors:
        print(f"errors: {len(errors)}", file=sys.stderr)
        for error in errors:
            print(f"  error: {error}", file=sys.stderr)
        return 1
    print("validation: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
