# Glean

Linked from `AGENTS.md` rule 8. Design: `docs/V1_4_DESIGN.md` §10. Skill: `@x-research`.

1. **Conceptual rounds first.** What does the application do? Which work happens in it? Which systems send it data, and which receive data from it? Which workflows and documents describe it?
2. **Integrate before you go deeper.** Turn the answers into evidence (`research integrate`), update the app brief and the models, then ask follow-up conceptual questions for the gaps.
3. **Columns last.** The framework explains columns itself first (`python -m b2s columns <app>`). Ask Glean only about columns marked `unclear`, grouped by table. The tool refuses other column rounds.
4. **Raw reply first.** Save the reply exactly as received (`research raw`) before you parse it. Never re-ask because a reply was lost.
5. **One JSON object per topic**, several rounds if needed, within the round budget. A closed round can reopen with a reason and an extra budget.
6. **Evidence rules.** A Glean claim is medium confidence at most. Its `root_source` is the document Glean cites; a Glean answer that summarises a document does not corroborate that document.
7. **Two channels.** Use the Glean connector when the chat has it. Otherwise show the request text; the worker pastes it into Glean and pastes the reply back (paste mode). Both write the same files.
8. Never put a sensitive value into a Glean request.
