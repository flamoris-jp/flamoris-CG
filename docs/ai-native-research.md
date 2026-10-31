# AI-native CG tool evolution: research charter

**Status: research question and experimental hypotheses, not implemented AI features.**

FLAMORIS-CG has two equally important purposes:

1. **Production:** create objects, animate them by script, and produce editable CG scenes and clips; ultimately explore lightweight modeling, physics and rendering.
2. **Research:** test **how CG tooling changes if it is designed for AI agents and humans together from the beginning**, instead of treating an AI as a macro recorder or attaching a chat box to a traditional modeling interface.

Blender is our initial experimental backend and reference point. We do not need to reimplement its geometry, simulation or rendering system to test interaction models.

## Central question

> When an AI is a normal user of the CG tool, what should its native abstractions, operations, editing model and feedback look like?

**"AI-native" is a hypothesis to test, not a claim of superiority.** Some tasks will still be faster or more expressive in a traditional interface. A good CG tool should retain direct human editing and visibility into what the AI changed.

## Candidate hypotheses (unproven)

| Hypothesis | Small experiment | What would count as useful evidence |
| --- | --- | --- |
| Semantic operations help more than raw API calls | Compare an explicit `move` or `bounce` action with a longer Blender-Python procedure | Shorter repeatable instruction, understandable results, fewer unintended edits |
| Inspectable scene state improves collaboration | Export object IDs, positions and motion from an experiment, ask an AI to revise one object only | Intended edit applied; unrelated state retained and verified |
| Declarative projects reduce regeneration | Change just one keyframe or material in the JSON scene and rebuild | Controlled diff in spec and artifacts; no ambiguous hidden steps |
| Reversible / bounded commands improve trust | Reject unsupported actions and duplicate IDs; preserve the original spec | Predictable failures, no overwritten output or arbitrary code execution |
| AI can select useful abstractions | Compare primitive, procedural, keyframe and Blender-physics solutions to the same small motion | Clear tradeoffs in editing effort, precision, repeatability and output |
| Human + AI editing should coexist | Edit the result in Blender, then assess which changes can be represented in the CG data model | Explicit supported/unsupported round-trip boundary, no silent data loss |

These are possible tests, not a commitment to implement every feature now. Do not claim AI planning, automatic optimization, physics, or Blender round-trip support until those features and their acceptance evidence exist.

## Practical experiment loop

1. Describe a small intended visual result (e.g. a red sphere moves across a scene).
2. Express it in a strict, versioned script or scene contract.
3. Run the experiment with Blender and record the command, version, artifacts and errors.
4. Inspect the produced scene or frames rather than assuming the run matches the intent.
5. Change one aspect (position, motion, model or physics setting), repeat, and compare.
6. Document what made the human/AI editing easier or harder, including failures.

**Compare solutions rather than counting tools.** Track time/steps, number of manual corrections, preservation of other scene state, reproducibility, portability and render cost as appropriate. Avoid benchmark claims without repeatable measurements.

## Boundary with Cinema

**CG evolves how one CG scene or clip is specified, edited and generated.** It may eventually support AI writing/revising scene data and checking rendered results.

**Cinema (paused) would own project-wide story, intent, orchestration across CG, KineticTypo, Generation and Kachinco.** No film director, project-level scenario engine or automatic multi-tool workflow belongs in CG just because the experiment is AI-native.

## Guardrails

- Prefer safe structured operations over arbitrary untrusted Blender Python.
- Keep human inspection and approval available; never silently overwrite source scenes.
- A generated clip is not proof that the requested artistic intention was fulfilled.
- Keep source-of-truth data and native Blender files separate, with documented import/export limits.
- AI-native must not mean AI-only: scripts, files and editable artifacts should remain understandable without a model.
- Distinguish present implementations, experimental observations and future hypotheses.

This charter is a guide for experiments. It does not authorize deployment, GPU use, running services or resuming Cinema.
