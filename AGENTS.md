# Agent instructions

This is a public, portable literature-prior workflow. Start with [the agent runbook](docs/agent_handoff.md) for acquisition, model review, retry, or handoff; use [the input contract](docs/input_contract.md) for database changes.

- Treat every search result and model response as a candidate. Preserve source, event, comparison, endpoint, uncertainty and review status. A quote match or a program `PASS` is not scientific verification; reporting rights are independent of these evidence states.
- Before acquisition, inspect the applicable source-scope decisions, access-stop registry and local assets. A stopped source cannot be accessed through another route; a separately qualified held asset can still be used within its recorded scope. Respect copyright and access controls.
- Bind each attempt to source, evidence, code and model identifiers. Create a new output directory for a retry and preserve failed, partial, negative and contradictory outcomes. Validate receipts before reuse; a hash proves byte consistency, not identity, permission or scientific truth.
- Review direction, named controls, experimental units, identity, figure/table evidence and contradictions against the relevant source and, where needed, original images. Mark missing or ambiguous details as unresolved; never convert nondetection of a difference into evidence of no effect.
- Keep private data, raw articles, model prompts and run outputs outside the published tree or under ignored directories. Before committing, check the exact file list, local paths, credentials and redistribution rights.
- Run `python3 -m unittest discover -s tests -v` after relevant code changes. These bounded tests do not qualify long unattended execution, process-tree cleanup, service supervision or scientific accuracy.
