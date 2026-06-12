# Function Plan (F1 – F21)

## Core analyzer (no LLM)

| # | Name | Status |
|---|---|:-:|
| F1 | `.dig` parser | Done |
| F2 | Circuit netlist + signal-flow graph | Done |
| F3 | Structural fact extractor | Done |
| F4 | Test-result parser | Done |

## Layer 1 deterministic checkers

| # | Name | Status |
|---|---|:-:|
| F5 | Wire completeness checker | Done |
| F6 | Bit-width consistency checker | Done |
| F7 | Combinational-loop checker | Done |
| F8 | Interface conformance checker | Done |
| F9 | Timing / sequential checker (register-clock-Q) | Done |
| F10 | K-map / Boolean simplification PRO | TBD |

## Layer 2 LLM conceptual explanation

| # | Name | Status |
|---|---|:-:|
| F11 | LLM client wrapper (SDK, prompt versioning, cost tracking etc.) | Done |
| F12 | Conceptual explanation generator | Done |
| F13 | Prompt-leakage guard | Done |

## Layer 3 LLM strategic debugging

| # | Name | Status |
|---|---|:-:|
| F14 | Failed-test interpreter | Data side done (fast per-row runner: failing rows + expected-vs-found cells); LLM side TBD (`/api/llm/debug` coordinator + hypothesis cards) |
| F15 | Test-writing coach | TBD |
| F16 | Signal-flow narrator | TBD |

## Research infrastructure

| # | Name | Status |
|---|---|:-:|
| F17 | UI design | Ongoing |
| F18 | Ablation condition controller | TBD |
| F19 | Telemetry logger | TBD (frontend event log exists; SQLite sink TBD) |
| F20 | Digital source-code dig (Path-3 plugin viability) | TBD |
| F21 | Evaluation harness | L2 benchmark harness done (`dlc/evaluator/`: 6-model competition, grader selection, Pareto plots) — awaiting the run; 30-bug L1/L3 ablation harness TBD |
| F22 | CLI interface | TBD |
