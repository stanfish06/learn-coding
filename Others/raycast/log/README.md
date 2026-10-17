# Log

Session records for the Raycast launcher reverse-engineering work. Each entry is written to be readable
cold, a week later, by someone who was not in the session.

| Date | Entry | Subject |
|---|---|---|
| 2026-10-17 | [search-core.md](2026-10-17-search-core.md) | Toolchain, metadata walk, fuzzy score, ranking, rules, CLI |

Conventions used across the log and the repo:

* **RECOVERED** — read out of the shipped binary. Every claim names its address and the evidence file.
* **GUESS** (G1–G8) — inference, listed in `README.md` and marked inline in `src/rank.swift`.
* **PENDING** — a mechanism that is recovered but whose numeric detail (table, constant) is not read yet.
* **CORRECTION** — something previously written in this repo that turned out to be wrong; kept visible
  rather than silently edited, because the failure mode is informative.

Evidence lives in `evidence/NN-*.md`; regenerable tooling in `tools/`; the demonstrator in `src/` with
assertions in `tests/`.
