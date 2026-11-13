# Files and versions

Linked from `AGENTS.md` rule 5. Design: `docs/V1_4_DESIGN.md` §7.

- No tables hold project state. Everything is a file in the project folder.
- A file that holds state is named `<name>.vNNN.<ext>` and is **written once**. Its sidecar `<name>.vNNN.meta.json` holds the content hash, the input versions it was made from, the reason, the event and the framework version.
- A new version is written only when the content changes. The latest version is the highest number.
- `.mmd`, `.html`, `.xlsx` with the same `vNNN` are generated from that version. Never edit them.
- Save your changes with `python -m b2s save <app> <stem> <file> --reason "<why>" --via genie`. The reason names the cause: `input IN-0004`, `answer Q-0012`, `worker request in chat`.
- A hand edit of a version file is detected (hash) and reported by `python -m b2s check <app>`.
- Every change is an event (`events/`). Events are never changed.
- Inbox files are read-only. New files from people go to `uploads/`.
- An approval covers exact versions. A new version needs a new approval; the old approval stays in the history.
