#!/usr/bin/env python3
"""Record locked-frame A/B/A/B DreamLoop comparisons; never self-judge."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) != 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"expected PNG image: {path}")
    return struct.unpack(">II", head[16:24])


def init(work, target, scene, shot, frame):
    work, target = Path(work), Path(target).resolve()
    if (work / "lock.json").exists():
        raise FileExistsError("locked target already exists: do not replace it")
    width, height = png_size(target)
    work.mkdir(parents=True, exist_ok=True)
    lock = {"target": str(target), "target_sha256": digest(target),
            "width": width, "height": height, "scene": scene, "shot": shot, "frame": frame}
    (work / "lock.json").write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return lock


def record(work, capture, variant, change, dream_loop, verdict=None):
    work, capture, dream_loop = Path(work), Path(capture).resolve(), Path(dream_loop)
    lock = json.loads((work / "lock.json").read_text())
    target = Path(lock["target"])
    if digest(target) != lock["target_sha256"]:
        raise ValueError("locked target has changed")
    w, h = png_size(capture)
    if abs(w / h - lock["width"] / lock["height"]) > 0.005:
        raise ValueError("capture aspect ratio differs from locked target")
    records = work / "abab.jsonl"
    previous = [json.loads(line) for line in records.read_text().splitlines()] if records.exists() else []
    expected = "A" if len(previous) % 2 == 0 else "B"
    if variant != expected:
        raise ValueError(f"ABAB ordering violated: expected {expected}, got {variant}")
    if change not in ("none", "camera", "massing", "material", "mesh"):
        raise ValueError("one change class per DreamLoop round")
    if variant == "A" and change != "none":
        raise ValueError("baseline A must have change class none")
    scripts = [dream_loop / "scripts" / name for name in ("overlay.py", "crop_gate.py")]
    if not all(s.is_file() for s in scripts):
        raise FileNotFoundError("DREAM_LOOP_ROOT must contain scripts/overlay.py and scripts/crop_gate.py")
    out = work / "overlays" / f"round-{len(previous) + 1:04d}"
    out.mkdir(parents=True, exist_ok=False)
    try:
        entry = _evaluate_round(capture, variant, change, verdict, previous, lock, target, out, scripts)
    except Exception:
        shutil.rmtree(out)
        raise
    with records.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def _evaluate_round(capture, variant, change, verdict, previous, lock, target, out, scripts):
    subprocess.run([sys.executable, str(scripts[0]), str(target), str(capture), str(out)], check=True)
    gate = subprocess.run([sys.executable, str(scripts[1]), str(target), str(capture), str(out)], check=False)
    if gate.returncode not in (0, 2):
        raise RuntimeError(f"crop_gate failed to run: exit {gate.returncode}")
    passed = gate.returncode == 0
    critic = json.loads(Path(verdict).read_text()) if verdict else None
    if critic is not None:
        if not isinstance(critic, dict):
            raise ValueError("critic verdict must be JSON object")
        if not passed and (critic.get("total") is not None or
                           any(k in critic.get("score", {}) for k in ("lighting", "materials", "details"))):
            raise ValueError("composition failed: no lighting/material/details/total verdict allowed")
        if passed and critic.get("total") is not None:
            score = critic.get("score", {})
            limits = {"composition": 3, "lighting": 3, "materials": 3, "details": 1}
            if any(not isinstance(score.get(k), (float, int)) or not 0 <= score[k] <= v for k, v in limits.items()):
                raise ValueError("invalid DreamLoop score fields")
            if abs(sum(score[k] for k in limits) - critic["total"]) > 0.01:
                raise ValueError("DreamLoop total is not the sum of category scores")
    return {"round": len(previous) + 1, "variant": variant, "change_class": change,
            "capture": str(capture), "capture_sha256": digest(capture),
            "target_sha256": lock["target_sha256"], "crop_gate_pass": passed,
            "judge": critic, "overlay_dir": str(out),
            "warning": "independent critic and visual overlay inspection required"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="cmd", required=True)
    setup = commands.add_parser("init")
    setup.add_argument("--work", required=True)
    setup.add_argument("--target", required=True)
    setup.add_argument("--scene", required=True)
    setup.add_argument("--shot", required=True)
    setup.add_argument("--frame", required=True, type=int)
    rnd = commands.add_parser("round")
    rnd.add_argument("--work", required=True)
    rnd.add_argument("--capture", required=True)
    rnd.add_argument("--variant", required=True, choices=("A", "B"))
    rnd.add_argument("--change", required=True, choices=("none", "camera", "massing", "material", "mesh"))
    rnd.add_argument("--dream-loop", required=True)
    rnd.add_argument("--verdict")
    args = ap.parse_args()
    result = (init(args.work, args.target, args.scene, args.shot, args.frame) if args.cmd == "init"
              else record(args.work, args.capture, args.variant, args.change, args.dream_loop, args.verdict))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
