# Prior experiments in flamoris-cinema: what to reuse and what not to copy

Cinema was paused on 2026-10-31 after clarifying that it should eventually own *project-wide intent and orchestration*, not the same level of CG clip production. Its implementation and evidence must remain preserved.

Source: [flamoris-cinema](https://github.com/flamoris-jp/flamoris-cinema) and [its pause/vision decision](https://github.com/flamoris-jp/flamoris-cinema/blob/main/docs/vision-and-pause.md).

## Useful evidence from the original Cinema prototype

- Offline Blender importer/exporter and sampled motion contracts.
- Sphere motion, multiple camera render and CPU/HIP acceptance.
- Glyph read-only shape integration and an early part-based walking performance.
- A native Blender 5.2.3 workflow, Flamenco render handoff and Kachinco CLI clip handoff.
- Explicit restrictions on source/scene ownership, unsupported Blender edits and separate real-device acceptance.

## Decision for this repo

**Do not copy the Cinema repository wholesale.** The existing source is strongly coupled to Cinema's scene/take formats and short-film milestones. A wholesale copy would inherit unnecessary Cinema authority and complexity, duplicate test histories and make Cinema's pause ambiguous.

Instead start with a deliberately small Blender experiment here. When a real CG feature needs an existing Cinema function:

1. Identify the exact existing function, its contract, tests, license and ownership.
2. Compare importing an existing shared utility, extracting a common library, or reimplementing a tiny independent adapter.
3. Document the choice, maintain provenance and add independent CG acceptance tests.
4. Keep Cinema's historical code and commitments untouched unless separately authorized.

The initial example deliberately uses a separate minimal JSON laboratory spec; it is **not** compatible with Cinema Scene/Take JSON. Unification is a later decision based on real use, not a requirement to begin.

## Legacy issue dependencies (2026-11-01)

[Scene Engine reconciliation](scene-engine-scope.md) maps Kachinco #124 and Glyph #3 to current owners and research gates. Inspect Cinema's existing Glyph adapter before selecting CG's read-only integration. It neither completes CG integration nor requires Cinema to resume. CG and Glyph can agree a minimum consumer contract without a universal Scene/Take schema.
