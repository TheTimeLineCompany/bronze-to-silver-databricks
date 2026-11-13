## What changes
Step(s): `P_._` · Checkpoint(s): `CP_` · Slot / plug-in (if any): `____`

## Checks
- [ ] `python -m pytest` passes.
- [ ] `python -m b2s.demo.walkthrough <folder>` ends with the handoff.
- [ ] Step `version` bumped in `b2s/steps.py` when a step's output changes (old outputs become stale on purpose).
- [ ] `FRAMEWORK_VERSION` and `CHANGELOG.md` updated.
- [ ] No real data in fixtures, samples or docs.

## For a contribution package from a worker
- [ ] Contract test passes on the package's sample output.
- [ ] Moved to `plugins/` with `origin: core` (or merged into the core plug-in of the slot).
