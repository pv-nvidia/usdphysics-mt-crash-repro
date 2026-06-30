# OpenUSD multithreaded `LoadUsdPhysicsFromRange` heap-corruption repro

Minimal, **self-contained** reproducer for a multithreaded crash in OpenUSD's
physics parsing (`UsdPhysics.LoadUsdPhysicsFromRange` / the
`UsdPhysicsParsingUtility` `_FinalizeCollisionDescs<...>` TBB `parallel_for`).

Triggered when a single rigid body has **many mesh colliders** beneath it and the
stage is parsed from multiple threads. Manifests as `SIGSEGV`,
`malloc_consolidate(): invalid chunk size`, `double free`, or
`malloc(): unaligned tcache chunk detected`.

No external assets required — the stage is generated in-memory.

This repo provides two equivalent reproducers:

- **`test_usd_4002.py`** — the actual upstream regression tests from
  [PR #4002](https://github.com/PixarAnimationStudios/OpenUSD/pull/4002)
  (`test_rigidbody_collision_multithreading_parse`,
  `test_custom_geometry_multithreading_parse`), adapted to run standalone with
  plain `unittest`. These also assert *correctness* (collider count + deterministic
  custom-token ordering), not just "doesn't crash". **Preferred.**
- **`repro.py`** — a minimal hand-rolled loop (one rigid body + N mesh colliders),
  handy for quick sweeps and tuning `COLLIDERS` / `N`.

## TL;DR

| USD runtime                     | namespace                 | multithreaded | single-thread |
| ------------------------------- | ------------------------- | ------------- | ------------- |
| `usd-core==25.11` (pip)         | `pxrInternal_v0_25_11`    | **CRASH 8/8** | clean         |
| `usd-exchange==2.3.0` (pip)     | `pxrInternal_v0_25_5`     | **CRASH 12/12** | clean       |
| Isaac Sim Kit `omni.usd.libs`   | `pxrInternal_v0_25_11`    | **CRASH 6/6** | clean         |
| `usd-core==26.5` (pip)          | `pxrInternal_v0_26_5`     | clean (0/400) | clean         |

The crash is fixed in **OpenUSD 26.05**
([PR #4002](https://github.com/PixarAnimationStudios/OpenUSD/pull/4002),
commit `060715faa77469b3f0e76fda4d1732f856570f88`,
*"[usdPhysics] fix for a multithreaded crash if one rigidbody has multiple
colliders beneath"*).

The fix is **not** backported into the USD 25.x runtimes that ship with Isaac Sim
Kit (`omni.usd.libs`) nor into the `usd-exchange` 2.3.0 wheel.

## Quick start

```bash
python3 -m venv .venv && . .venv/bin/activate

# vulnerable: crashes (process dies before any assertion runs)
pip install 'usd-core==25.11'
python -m unittest test_usd_4002 -v   # SIGSEGV / malloc corruption
python repro.py                       # same, hand-rolled loop

# fixed
pip install 'usd-core==26.5'
python -m unittest test_usd_4002 -v   # OK
python repro.py                       # COMPLETED

# workaround on a vulnerable runtime: force single-threaded parsing
PXR_WORK_THREAD_LIMIT=1 python repro.py   # clean
```

Or sweep both versions automatically:

```bash
./run.sh
```

## Sweep across multiple USD runtimes

`run_all_usd.sh` runs the PR #4002 tests against several USD runtimes (each pip
runtime in its own throwaway venv) and prints a verdict table:

```bash
./run_all_usd.sh
# or customize:
RUNS=8 USD_CORE_VERSIONS="25.5 25.8 25.11 26.3 26.5" ./run_all_usd.sh
```

Example output:

```
usd-core==25.11        USD 25.11   pass=0 crash=6 err=0 /6  -> VULNERABLE
usd-core==26.5         USD 26.5    pass=6 crash=0 err=0 /6  -> OK (fixed)
usd-exchange==2.3.0    USD 25.5    pass=0 crash=6 err=0 /6  -> VULNERABLE
```

To also test **Isaac Sim Kit's bundled `omni.usd.libs`** (the USD the sim actually
loads at runtime), point the script at a python that can `from pxr import ...`
under Kit:

```bash
KIT_PYTHON=/path/to/isaac/python ./run_all_usd.sh
```

(In practice Kit's USD 25.11 is **VULNERABLE** too — measured 6/6 crash — which is
why the fix has to land in `omni.usd.libs` / `omni.usdex.libs`, not just the pip
wheels.)

## Knobs (env vars)

- `N` — number of parse iterations per run (default `50`). More iterations = higher
  crash probability per run.
- `COLLIDERS` — number of mesh colliders under the single rigid body (default `40`).
  The race needs "many" (>~30) colliders under one body.
- `PXR_WORK_THREAD_LIMIT=1` — OpenUSD knob that disables the work-thread pool;
  serializes the parse and avoids the race (workaround).

## What it does

`repro.py` builds an in-memory stage with one `/World/Body` carrying
`RigidBodyAPI`, and `COLLIDERS` child `Mesh` prims each with `CollisionAPI` +
`MeshCollisionAPI`. It flattens the stage and calls
`UsdPhysics.LoadUsdPhysicsFromRange(stage, ["/World"], excludePaths=[])` in a loop.
With the default (multithreaded) work pool this races inside
`_FinalizeCollisionDescs<UsdPhysicsMeshShapeDesc>`.

## Context

Originally surfaced in an Isaac Lab + Newton tablecloth workload: Newton's USD
importer (`newton/_src/utils/import_usd.py`) calls `LoadUsdPhysicsFromRange` while
building the scene, and the robot/cloth assets put many mesh colliders under one
body. The crash happens before the first sim step.

Because Isaac Sim Kit uses **its own bundled `omni.usd.libs`** (USD 25.11) at
runtime — not the pip `usd-core`/`usd-exchange` wheel — the fix must land in the
USD that Kit actually loads (`omni.usd.libs`, and `omni.usdex.libs`), either by
backporting `060715f` into the 25.11 build or by uplifting bundled OpenUSD to
>= 26.05.
