# Patch Loop Golden Dataset

This dataset defines baseline replay inputs for patch-loop stability checks.

## Session Files

Curated replay set (committed for deterministic CI):

- `tests/fixtures/patch_loop_sessions/20260408T200542318221Z_c321056b59d14dfb84540ce1022d64d0.json`
- `tests/fixtures/patch_loop_sessions/20260408T200557665187Z_a30ab2b608a4477b845f1118a6945267.json`
- `tests/fixtures/patch_loop_sessions/20260408T200617182734Z_709189204fd54a83a042eba2848c0dad.json`
- `tests/fixtures/patch_loop_sessions/20260408T200638514862Z_f67b268fb0154c71ba9d733a92f2f088.json`
- `tests/fixtures/patch_loop_sessions/20260408T200701600472Z_e4e58017aa0b4e268e94299d99f26d2f.json`
- `tests/fixtures/patch_loop_sessions/20260408T200722021373Z_d4e9d68517564752bd6427f398d69582.json`
- `tests/fixtures/patch_loop_sessions/20260408T200736794223Z_d5868db9444b44579350e5cd10b698cb.json`

## Replay Command

```bash
python scripts/evaluate_patch_loop.py ^
  --sessions-dir tests/fixtures/patch_loop_sessions ^
  --min-parsed-rate 0.80 ^
  --max-analysis-only-rate 0.05
```
