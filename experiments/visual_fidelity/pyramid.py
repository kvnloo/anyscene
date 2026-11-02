#!/usr/bin/env python3
"""Create/audit an immutable single-master Deep Zoom candidate (local, opt-in)."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dzi_info(path):
    root = ET.parse(path).getroot()
    size = next((x for x in root if x.tag.rsplit("}", 1)[-1] == "Size"), None)
    if size is None:
        raise ValueError("DZI Size missing")
    return {"width": int(size.attrib["Width"]), "height": int(size.attrib["Height"]),
            "tile_size": int(root.attrib["TileSize"]),
            "overlap": int(root.attrib["Overlap"]), "format": root.attrib["Format"]}


def check_tiles(folder, info):
    if min(info["width"], info["height"], info["tile_size"]) <= 0 or info["format"] != "webp":
        raise ValueError("invalid DZI dimensions or format")
    max_level = math.ceil(math.log2(max(info["width"], info["height"])))
    expected = 0
    for level in range(max_level + 1):
        divisor = 2 ** (max_level - level)
        w, h = math.ceil(info["width"] / divisor), math.ceil(info["height"] / divisor)
        nx, ny = math.ceil(w / info["tile_size"]), math.ceil(h / info["tile_size"])
        for y in range(ny):
            for x in range(nx):
                tile = folder / str(level) / f"{x}_{y}.webp"
                if not tile.is_file() or tile.stat().st_size == 0:
                    raise ValueError(f"missing/empty Deep Zoom tile: {tile}")
        expected += nx * ny
    actual = sum(1 for x in folder.rglob("*.webp") if x.is_file())
    if actual != expected:
        raise ValueError(f"DZI tile count differs: expected {expected}, found {actual}")
    return expected


def audit(folder, master=None):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    info = dzi_info(folder / "inspection.dzi")
    if info != manifest["dzi_info"]:
        raise ValueError("DZI metadata changed")
    count = check_tiles(folder / "inspection_files", info)
    if count != manifest["tile_count"]:
        raise ValueError("DZI tile count changed")
    if not (folder / "plate.webp").is_file() or (folder / "plate.webp").stat().st_size == 0:
        raise ValueError("missing/empty plate")
    if master is not None and digest(master) != manifest["master_sha256"]:
        raise ValueError("master hash does not match registered source")
    return manifest


def compile_source(master, output, scene, shot, vips="vips", tile_size=512, quality=85):
    master, output = Path(master).resolve(), Path(output).resolve()
    if not master.is_file():
        raise FileNotFoundError(master)
    if output.exists():
        raise FileExistsError(f"candidate already exists: {output}; never overwrite a source family")
    if not shutil.which(vips):
        raise RuntimeError("libvips CLI not found (install vips)")
    if tile_size not in (256, 512, 1024) or not (1 <= quality <= 100):
        raise ValueError("unsupported tile size or WebP quality")
    master_sha = digest(master)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".inspection-", dir=output.parent) as work:
        stage = Path(work) / "candidate"
        stage.mkdir()
        subprocess.run([vips, "dzsave", str(master), str(stage / "inspection"),
                        "--tile-size", str(tile_size), "--overlap", "1",
                        "--suffix", f".webp[Q={quality}]"], check=True)
        subprocess.run([vips, "thumbnail", str(master), str(stage / "plate.webp"), "1024"], check=True)
        info = dzi_info(stage / "inspection.dzi")
        if info["tile_size"] != tile_size or info["overlap"] != 1:
            raise ValueError("unexpected Deep Zoom geometry")
        count = check_tiles(stage / "inspection_files", info)
        manifest = {"schema": "anyscene.inspection.v1", "status": "candidate",
                    "scene": scene, "shot": shot, "master_file": master.name,
                    "master_sha256": master_sha, "source_family": master_sha[:16],
                    "dzi_info": info, "tile_count": count,
                    "dzi": "inspection.dzi", "plate": "plate.webp",
                    "tiles": "inspection_files", "note": "provenance only; no visual or mobile acceptance"}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        audit(stage, master)
        stage.rename(output)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    subs = ap.add_subparsers(dest="cmd", required=True)
    build = subs.add_parser("compile")
    build.add_argument("--master", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--scene", required=True)
    build.add_argument("--shot", required=True)
    build.add_argument("--vips", default="vips")
    build.add_argument("--tile-size", type=int, default=512, choices=(256, 512, 1024))
    build.add_argument("--quality", type=int, default=85)
    verify = subs.add_parser("audit")
    verify.add_argument("--folder", required=True)
    verify.add_argument("--master")
    args = ap.parse_args()
    result = (compile_source(args.master, args.output, args.scene, args.shot, args.vips, args.tile_size, args.quality)
              if args.cmd == "compile" else audit(args.folder, args.master))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
