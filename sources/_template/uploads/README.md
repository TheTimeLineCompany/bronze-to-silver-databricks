# uploads/ - files from people

Put files here that a person filled in or brought: a filled scope sheet, a note, an extract, a list of codes.

Then in `00_start_here` set **action** `register-uploads` and **purpose**:
| purpose | What happens |
|---|---|
| `instruction` | a standing instruction (IN-xxx) for **step** (or all steps) that points to the file |
| `feedback` | a feedback item on **checkpoint** (default: the current one) with the file attached; causes a rerun |
| `handover` | the file is copied to `<phase>/handover/` and passed to the next stage |

A filled scope sheet (columns `table, column, scope` or `table, scope`) is applied to discovery directly.
Each file is registered once (by content hash, in `registered.yaml`). After registering, Genie asks you a few questions about it (`@x-clarify`).
