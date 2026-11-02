"""Mocked contract tests; no Blender, libvips, GPU, browser or visual-quality claim."""
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pyramid
import record


def fake_png(path, w=128, h=128):
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", w, h) + b"\0" * 12)


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.work = self.root / "run"
        self.target = self.root / "target.png"
        self.capture = self.root / "capture.png"
        fake_png(self.target)
        fake_png(self.capture)
        self.dream = self.root / "dream"
        (self.dream / "scripts").mkdir(parents=True)
        for p in ("overlay.py", "crop_gate.py"):
            (self.dream / "scripts" / p).write_text("# stub\n")
        record.init(self.work, self.target, "test-scene", "shot", 1)

    @patch.object(record.subprocess, "run", return_value=SimpleNamespace(returncode=0))
    def test_abab_and_judge(self, _run):
        verdict = self.root / "verdict.json"
        verdict.write_text(json.dumps({"score": {"composition": 2.5, "lighting": 2, "materials": 2, "details": .5}, "total": 7}))
        for i, variant in enumerate("ABAB"):
            value = record.record(self.work, self.capture, variant, "none" if variant == "A" else "material", self.dream, verdict)
            self.assertEqual(value["round"], i + 1)
            self.assertTrue(value["crop_gate_pass"])
        self.assertEqual(len((self.work / "abab.jsonl").read_text().splitlines()), 4)
        with self.assertRaisesRegex(ValueError, "expected A"):
            record.record(self.work, self.capture, "B", "material", self.dream, verdict)

    @patch.object(record.subprocess, "run", return_value=SimpleNamespace(returncode=0))
    def test_target_lock_and_aspect(self, _run):
        fake_png(self.capture, 192, 128)
        with self.assertRaisesRegex(ValueError, "aspect"):
            record.record(self.work, self.capture, "A", "none", self.dream)
        fake_png(self.target, 144, 144)
        with self.assertRaisesRegex(ValueError, "locked target has changed"):
            record.record(self.work, self.capture, "A", "none", self.dream)

    @patch.object(record.subprocess, "run", side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=2)])
    def test_failed_crop_rejects_full_critic_and_cleans_up(self, _run):
        verdict = self.root / "verdict.json"
        verdict.write_text(json.dumps({"total": 8, "score": {"composition": 2, "materials": 3}}))
        with self.assertRaisesRegex(ValueError, "composition failed"):
            record.record(self.work, self.capture, "A", "none", self.dream, verdict)
        self.assertFalse((self.work / "overlays" / "round-0001").exists())
        self.assertFalse((self.work / "abab.jsonl").exists())


class PyramidTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.master = self.root / "master.png"
        self.master.write_bytes(b"image-master-example")
        self.output = self.root / "output"

    def fake_run(self, args, check):
        self.assertTrue(check)
        if args[1] == "dzsave":
            base = Path(args[3])
            base.with_suffix(".dzi").write_text('<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" TileSize="512" Overlap="1" Format="webp"><Size Width="2" Height="2" /></Image>')
            for level in (0, 1):
                tiles = base.parent / (base.name + "_files") / str(level)
                tiles.mkdir(parents=True)
                (tiles / "0_0.webp").write_bytes(b"tile")
        elif args[1] == "thumbnail":
            Path(args[3]).write_bytes(b"plate")
        return SimpleNamespace(returncode=0)

    def test_audit_refuses_tampered_source_and_missing_tiles(self):
        with patch.object(pyramid.shutil, "which", return_value="/usr/bin/vips"), patch.object(pyramid.subprocess, "run", side_effect=self.fake_run):
            result = pyramid.compile_source(self.master, self.output, "scene", "hero")
        self.assertEqual(result["tile_count"], 2)
        self.assertEqual(pyramid.audit(self.output, self.master)["status"], "candidate")
        with self.assertRaises(FileExistsError):
            pyramid.compile_source(self.master, self.output, "scene", "hero")
        self.master.write_bytes(b"new-master-different")
        with self.assertRaisesRegex(ValueError, "master hash"):
            pyramid.audit(self.output, self.master)
        (self.output / "inspection_files" / "1" / "0_0.webp").unlink()
        with self.assertRaisesRegex(ValueError, "missing/empty"):
            pyramid.audit(self.output)

    def test_invalid_metadata(self):
        with self.assertRaisesRegex(ValueError, "invalid DZI"):
            pyramid.check_tiles(self.root, {"width": 0, "height": 1, "tile_size": 512, "format": "webp"})


if __name__ == "__main__":
    unittest.main()
