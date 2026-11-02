# AnyScene × DreamLoop × Gigapixel — downstream experiments

This is an **opt-in research lane**, not a replacement for AnyScene's production builder. No changes to the endpoint, render farm, AnyShot/AnyKit-synced files or upstream. Generated scenes, images, tiles, evaluations and GPU traces remain untracked.

## Evidence and guardrails

- AnyScene already has render → diagnose → scripted fix → independent critic in [CRAFT](../../builder/CRAFT.md) and [PROMPT](../../builder/PROMPT.md). Build on it rather than adding a second production agent.
- [DreamLoop](https://github.com/kvnloo/dream-loop) adds a single locked frame/camera, overlay, crop gate, one change class per round, rollback and append-only unsuccessful attempts. Its edge-based crop gate is heuristic, **not** proof of camera registration.
- [Quackles #42](https://github.com/kvnloo/quackles/issues/42), [#43](https://github.com/kvnloo/quackles/issues/43), [#44](https://github.com/kvnloo/quackles/issues/44), [#45](https://github.com/kvnloo/quackles/issues/45) and [#53](https://github.com/kvnloo/quackles/issues/53): keep the Blender scene as authority; never mix 201MP/1GP masters across LOD; no decode/upload publication while moving; record phone performance. [The VT spike](https://github.com/kvnloo/quackles/blob/preview/rfc-003-realtime/docs/rfcs/003-spike-results.md) found that 8K textures still missed Cycles metals/glass and synchronous feedback readback caused frame hitches.
- [z0dream](https://github.com/kvnloo/z0dream)'s recursively generated equivalent local resolution is not literal gigapixel source imagery.
- [StableGen](https://github.com/sakalond/StableGen) is an optional **external** GPL tool. Never vendor its GPL code into MIT AnyScene; check its Blender/ComfyUI/model-license compatibility separately. Do not change the default Blender 5.0 setup; use an isolated compatible installation for that challenger.

## First A → B → A → B experiments

| Priority | Control A | Intervention B | Proof / reject condition |
| --- | --- | --- | --- |
| **E0: control** | An actual fixed-camera AnyScene still | Identical still via experiment tools | Must preserve target SHA/crop, pass unchanged-image gate; no fidelity claim. |
| **E1: hero material** | Stock 2K prop/material on *one* metal, stone, or fabric hero | High-res smartphone/DSLR reference → delit albedo + physical normal/roughness, optionally StableGen | Compare with locked camera/light; verify raking-light close-up and **second held-out camera**. Reject baked highlights, lettering, invented geometry, seams, color/material drift. |
| **E2: one-master deep inspection** | Fixed Cycles 4K/8K still | Same shot at 8K/16K then derive **one** plate and WebP DZI hierarchy | Verified master/hash, crop/color continuity, sharp viewport, tile bytes and time-to-sharp; never mix LOD source families. A real 1GP master is optional *later*, only if smaller studies win. |
| **E3: genuine 3D macro** | Scene GLB with 2K/4K maps | High-res UV material tiles loaded by visible footprint | Free camera remains responsive; no synchronous readPixels during motion, stale publication, unbounded texture residency, or material regression. Benchmark on physical Android. |

ABAB rules: same `.blend`/script SHA, camera rig/shot/frame, render engine/samples, light, color transform, target crop, output aspect and source master within each A/B. A is restored before B is repeated; record negative/rollback outcomes. Only **one** intervention class per DreamLoop round. Fresh independent critics score composition (0–3), lighting (0–3), materials (0–3), detail (0–1); do not judge materials until the crop gate passes. Evaluate a second camera / second lighting condition separately as a holdout, not by moving the locked target. For close performance comparisons, use 5+ valid runs and report variance. No cloud spend required for E0.

## Commands

```bash
# In kvnloo/anyscene checkout, with a local DreamLoop checkout next to it
python experiments/visual_fidelity/record.py init \
  --work .dream-loop/repair-hero --target /abs/path/target.png \
  --scene tokyo-electronics-repair --shot hero --frame 1

# Four locked rounds: A, B, A, B. Capture stills from the same camera.
python experiments/visual_fidelity/record.py round \
  --work .dream-loop/repair-hero --capture /abs/path/baseline.png \
  --variant A --change none --dream-loop ../dream-loop
python experiments/visual_fidelity/record.py round \
  --work .dream-loop/repair-hero --capture /abs/path/candidate.png \
  --variant B --change material --dream-loop ../dream-loop \
  --verdict /abs/path/fresh-independent-verdict.json
# Repeat A and B for rounds 3 and 4.

# Use a single high-quality rendered master for every DZI level.
# Requires libvips CLI, keeps all derivatives under ignored out/.
python experiments/visual_fidelity/pyramid.py compile \
  --master /abs/path/hero-master.png \
  --output out/inspection/repair-hero-v1 \
  --scene tokyo-electronics-repair --shot hero --tile-size 512
python experiments/visual_fidelity/pyramid.py audit \
  --folder out/inspection/repair-hero-v1 \
  --master /abs/path/hero-master.png

python -m unittest discover -s experiments/visual_fidelity -p 'test_*.py' -v
```

`record.py` SHA-locks the target, validates aspect, invokes **actual DreamLoop** `overlay.py` and `crop_gate.py`, enforces ABAB change classes and appends a JSONL receipt. It does **not** render, obtain critic verdicts or prove identical Blender cameras.

`pyramid.py` generates a `vips dzsave` WebP pyramid and a `vips thumbnail` plate from **one original file**. It validates DZI geometry and file presence plus master SHA. It **does not** prove pixel continuity, seam/color registration, client rendering or performance. Keep all output status `candidate`, never production by default.

**Promotion requires**: locked-scene and camera metadata; four comparable A/B/A/B captures and blind critic receipts; realistic multi-view/material behavior; same-master geometry and **additional visual** pyramid audits; browser first-correct-visual/time-to-sharp, p95/p99/max frame times, frames >33ms and >50ms, bytes/cache/decode; and physical-phone measurements. Do not edit shared renderer copies or default endpoints before the challenger wins.

**Not run:** Blender GPU render, StableGen/ComfyUI, fal, live libvips, browser and physical-phone tests. The generated .blend/assets used by the reference scenes are not in Git.
