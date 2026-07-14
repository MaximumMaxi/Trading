# Team Workflow

Two people, two machines, one repo.

## Roles

| | Maxwell's machine | Melchi's machine |
|---|---|---|
| **Person** | Maxwell — FX / strategy brain | Melchi — runs the code |
| **Has** | Claude (code + analysis), the dev/repo hub | MT5 terminal, real cached data, broker connection |
| **Owns** | strategy design, code authoring, reasoning about results | **all execution**: `data.loader`, `backtest`, `walk_forward`, `diagnose`, `live.bot` |

**Key fact:** anything that needs *real data* or the *broker* runs on **Melchi's
machine only**. Maxwell's machine writes and reviews code and can run synthetic
tests, but does not have the market data or MT5.

Claude runs **only on Maxwell's machine** and cannot see or touch Melchi's files.
A second Claude session could be run *on* Melchi's machine if needed — it would be
a separate instance, sharing nothing but this repo.

## The loop

```
  Maxwell + Claude (design/code)            Melchi (run/report)
 ┌────────────────────────────┐  push    ┌────────────────────────────┐
 │ 1. design strategy / edit   │ ───────► │ 3. git pull                 │
 │    code, verify (synthetic) │          │ 4. run data/backtest/WF/bot │
 │ 2. git commit + push        │ ◄─────── │ 5. commit results / paste   │
 │ 6. read results, iterate    │  results │    output back              │
 └────────────────────────────┘          └────────────────────────────┘
```

1. **Design & code** — Maxwell's FX ideas → Claude implements + verifies on
   synthetic data → commit + push to `main`.
2. **Run** — Melchi `git pull`, runs the relevant module on real data / MT5.
3. **Report back** — Melchi shares results one of two ways:
   - **paste** the terminal output into the Maxwell/Claude session, or
   - **commit** the result files and push (see "Sharing results" below).
4. **Iterate.**

## Sharing results (Melchi → Maxwell)

Result artifacts are git-ignored by default (they're generated), so to share them
deliberately, force-add the specific file:

```powershell
git add -f logs/bt_trades.csv logs/wf_oos_trades.csv
git commit -m "results: walk-forward run <date>"
git push
```

Then Maxwell pulls and Claude reads them. **Never** `git add -f` `secrets.py`,
`specs.json` with live account context, or anything with credentials.

For quick questions, pasting the terminal output is faster than committing.

## Ownership / avoiding collisions

- **`config/settings.py` is the shared control panel** (universe, params,
  DRY_RUN). Treat changes to it as deliberate; mention them in the commit message.
  If both edit it, coordinate — it's the most likely merge-conflict file.
- **`secrets.py` is per-machine and never committed.** Each machine keeps its own.
- **Melchi owns `DRY_RUN`.** Flip to `False` only on Melchi's machine when
  intentionally going live on the demo.
- Push small, described commits. Pull before you start editing.

## Optional: give Claude real backtest ability on Maxwell's machine

Today Claude can only run *synthetic* tests here (no market data). To let it run
**real** backtests locally, copy the data cache over once:

- On Melchi's machine, zip `data/cache/` + `config/specs.json`.
- Drop them into the same paths on Maxwell's machine.

Refresh whenever Melchi pulls fresh bars. (This is a manual copy, not git — the
data stays out of the repo.)
