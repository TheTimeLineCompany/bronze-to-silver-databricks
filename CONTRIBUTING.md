# Contributing

The framework lives in Git and is changed by a small group of **maintainers**. Workers download a release into their
Databricks workspace and do not commit to it. Their improvements come back as **contribution packages**
(`@fw-integrate` worker mode → `contrib/<name>-<version>-<date>.zip`) or as feedback.

## Maintainers: before you open a pull request
1. `pip install -r requirements-ci.txt`
2. `python -m pytest` — the whole suite, including the end-to-end run of the fake application and the privacy scan.
3. `python -m b2s.demo.walkthrough <empty folder>` — must end with the handoff.
4. A framework change that changes what a step produces: bump that step's `version` in `b2s/steps.py` (it marks old outputs stale) and `FRAMEWORK_VERSION`, and add a line to `CHANGELOG.md`.
5. Keep `AGENTS.md` under 6,000 characters (a test checks it); details go to `rules/`.

## Integrating a contribution package (`@fw-integrate` maintainer mode)
1. Unpack it; run its contract test (`b2s.plugins.contract_test`) and the full suite.
2. Move it to `plugins/` with `origin: core`, or merge it into an existing core plug-in.
3. A new slot needs a contract in `b2s/plugins.py` (`SLOTS`), a contract test, a design note, and a test.

## Rules
- **No real data.** Examples, fixtures and sample outputs must be fictional. Never commit client documents, bronze extracts or personal data.
- **Guarantees go in code.** A rule an agent must follow needs a check and a test, not only a sentence in a skill.
- **The V1.3 sequence stays** (P0–P6, CP1–CP6). Upgrades go inside the steps.
- **Write plainly.** Docs and skills use short sentences in simple technical English (ASD-STE100 style).

## Reporting security or privacy issues
Do not open a public issue for a problem that could expose personal data. Contact the maintainers privately.
