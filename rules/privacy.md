# Privacy

Linked from `AGENTS.md` rule 3. Design: `docs/V1_4_DESIGN.md` §14.

- Sensitive classes: `personal_data`, `secret_or_token`, `application_log`, `payload_or_free_text`. They are found from the column name, the share of values that look like email, phone, IP, user agent, URL, JSON or token, and Unity Catalog tags and masks.
- The P2 notebook removes values of sensitive columns **before** it writes anything. Only shapes and ratios are kept. Top values are written only for low-cardinality code, status and type columns, never for keys.
- Never copy a value of a sensitive column into any file, item, question, Glean request or chat message. Describe it by its shape (`aaaa@aaa.aaa`) or its share.
- The project folder must not be under `/Workspace/Shared`.
- At CP2 every personal-data column that goes to silver needs a handling: `keep_tagged`, `mask` or `hash`, with a reason. Secrets never go to silver.
- Document extracts are redacted the same way (emails and phone numbers become shapes).
