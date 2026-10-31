# Contributing

Thank you for helping. This project is used on real bronze-to-silver programmes, so changes must keep the gates reliable.

## Before you open a pull request
1. `pip install -r requirements-ci.txt` (add `pyspark==3.5.*` for the Spark tests).
2. Run all checks:
   ```bash
   python -m pytest -q tests/                  # add RUN_SPARK=1 for the discovery tests
   python tools/x_ontology_check.py            # must print ONTOLOGY COHERENT
   python tools/p4_2_validate_sttm.py --all
   python tools/x_validate_gate.py             # must print CHECKPOINTS CONSISTENT
   ```
3. If you change a tool that writes example outputs, regenerate them (`python tools/x_checkpoint_pack.py <source> --all`, `... global --all`, `... board`).
4. Keep `AGENTS.md` under 20,000 characters (the Genie Code limit).

## Rules
- **No real data.** Examples, fixtures, and test data must be fictional. Never commit client documents, bronze extracts, or personal data.
- **Guarantees go in code.** A new rule an agent must follow needs a validator or gate check and a test, not only a sentence in a skill.
- **Write plainly.** Docs and skills use short sentences in simple technical English (ASD-STE100 style).
- One topic per pull request. Describe what changed and how you tested it.

## Good first contributions
- Value-kind patterns for more personal-data types (national ids, IBAN, addresses) with tests.
- More source-system examples (fictional): ERP, WMS, TMS, CRM.
- Adapters for other agent runtimes (the discovery card runner, the clarify step).
- Translations of the checkpoint pack labels.

## Reporting security or privacy issues
Do not open a public issue for a problem that could expose personal data. Contact the maintainers privately through GitHub.
