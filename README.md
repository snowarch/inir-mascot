# inir-mascot

Official art pack for **Kira**, the mascot of the [iNiR](https://github.com/snowarch/iNiR) desktop shell.

This repository contains the finished images and animations distributed to iNiR users. The shell downloads the latest published pack as an optional component.

<p align="center">
  <img src="./inir-mascot-base.png" width="220" alt="Kira">
</p>

## Repository contents

| Path | Description |
|---|---|
| `inir-mascot-*.png` | Static mascot poses |
| `inir-mascot-*.gif` | Animated mascot loops |
| `CATALOG.md` | Visual index of the published collection |
| `STREET.md` | Classification of the street art line |
| `CHANGELOG.md` | Published pack history |

The release archive contains only the finished top-level `inir-mascot-*.png` and `inir-mascot-*.gif` files. Runtime behavior, dialogue, pose selection, settings and integration logic belong to the iNiR repository.

## Releases

Published releases provide the mascot archive plus integrity metadata used by iNiR's optional Extras installer. Published asset filenames are stable and releases are additive so older iNiR versions can safely ignore newer art.

## Asset format

Published static assets use the runtime format expected by iNiR:

- maximum dimension of 640 pixels;
- indexed PNG with transparency;
- flat filenames using `inir-mascot-<pose>.png`;
- animated assets using `inir-mascot-<animation>.gif`.

Some older published assets are retained for compatibility even when they predate the current optimization rules.

## Branding

Kira is original iNiR product artwork. The assets in this repository are intended for iNiR-related use and are not a general-purpose character pack.
