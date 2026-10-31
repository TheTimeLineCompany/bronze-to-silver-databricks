# registry - shared model and project state (global)

| Path | Holds | Changed by |
|---|---|---|
| `ontology/` | business, data, and information ontology (see `ontology/README.md`) | change request + PR |
| `entities.yaml` | shared master entities (P3) | change request, CP3 |
| `key_normalisation.yaml` | key rules and survivorship (P3) | change request, CP3b |
| `sources.yaml` | all sources, business scope, checkpoint status | PR only |
| `open_questions.yaml` | questions for the client | anyone adds; owner answers |
| `decisions.md` | decision log | add only |
| `change_requests/` | CR-nnn.md from p3-1-entity-model | data architects |
| `feedback/<CP>/` | feedback and upstream issues for CP3 / CP3b | reviewers, agents |
| `checkpoint/` | packs for CP3_central_model and CP3b_key_rules (`tools/x_checkpoint_pack.py global --all`) | code |
| `board/` | feedback board: all feedback and upstream issues (`tools/x_checkpoint_pack.py board`) | code |
