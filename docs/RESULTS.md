# ACORN evaluation results (updated 2026-08-20)

Model-matched four-condition ablation over **all 10 Amazon SOP-Bench
domains**. All graded against the packs' labeled dev sets; compliance is
audited by the same contract library in observe mode across every
condition. Conditions: `baseline` (SOP in prompt, plain tool loop),
`passive` (validate-only: block + reprompt), `mask` (dynamic tool
exposure, no jump), `acorn` (mask + symbolic jump-forward with binders).
Mask granularity: `step` throughout (the paper's headline setting; see
the granularity spectrum below).

## Amazon SOP-Bench: 10-domain × 4-condition matrix

| domain | model | condition | n | TSR | calls/row | sym ratio | proc-clean | tokens | est. cost | avg latency | ctrl share | state reuse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dangerous_goods | gpt-5-mini | acorn | 274 | **100.0%** | 0.99 | 0.50 | 100% | 501,018 | $0.30 | – | – | – |
| dangerous_goods | gpt-5-mini | mask | 274 | **81.8%** | 1.99 | 0.00 | 100% | 992,265 | $0.60 | 14.4s | 0.0002 | 0.93 |
| dangerous_goods | gpt-5-mini | passive | 274 | **85.4%** | 2.99 | 0.00 | 100% | 1,658,938 | $1.00 | 16.8s | 0.0001 | 0.91 |
| dangerous_goods | gpt-5-mini | baseline | 274 | **84.7%** | 2.98 | 0.00 | 100% | 1,671,981 | $1.00 | – | – | – |
| customer_service | gpt-5-mini | acorn | 156 | **100.0%** | 5.44 | 0.16 | 100% | 2,162,452 | $1.30 | 31.5s | 0.0003 | 0.48 |
| customer_service | gpt-5-mini | mask | 156 | **69.9%** | 6.39 | 0.00 | 100% | 2,727,985 | $1.64 | 62.0s | 0.0001 | 0.47 |
| customer_service | gpt-5-mini | passive | 156 | **69.9%** | 7.39 | 0.00 | 100% | 4,166,792 | $2.50 | 33.4s | 0.0001 | 0.46 |
| customer_service | gpt-5-mini | baseline | 156 | **68.6%** | 7.28 | 0.00 | 73% | 4,023,794 | $2.41 | 25.9s | 0.0003 | 0.97 |
| patient_intake | gpt-5-mini | acorn | 66 | **100.0%** | 3.73 | 0.21 | 100% | 605,381 | $0.36 | 32.0s | 0.0003 | 0.90 |
| patient_intake | gpt-5-mini | mask | 66 | **100.0%** | 4.73 | 0.00 | 100% | 726,955 | $0.44 | 38.0s | 0.0002 | 0.90 |
| patient_intake | gpt-5-mini | passive | 66 | **43.9%** | 2.89 | 0.00 | 100% | 523,012 | $0.31 | 20.3s | 0.0001 | 0.85 |
| patient_intake | gpt-5-mini | baseline | 66 | **45.5%** | 2.94 | 0.00 | 98% | 539,312 | $0.32 | 21.9s | 0.0001 | 0.93 |
| know_your_business | gpt-5-mini | acorn | 90 | **55.6%** | 1.00 | 0.89 | 100% | 302,716 | $0.18 | 8.8s | 0.0003 | 0.20 |
| know_your_business | gpt-5-mini | mask | 90 | **51.1%** | 9.10 | 0.00 | 100% | 2,038,253 | $1.22 | 36.2s | 0.0001 | 0.21 |
| know_your_business | gpt-5-mini | passive | 90 | **50.0%** | 8.50 | 0.00 | 100% | 2,708,953 | $1.63 | 38.4s | 0.0001 | 0.19 |
| know_your_business | gpt-5-mini | baseline | 90 | **50.0%** | 8.24 | 0.00 | 81% | 2,584,471 | $1.55 | 32.4s | 0.0002 | 0.96 |
| aircraft_inspection | gpt-5-mini | acorn | 112 | **99.1%** | 4.19 | 0.19 | 100% | 1,412,915 | $0.85 | 48.2s | 0.0001 | 0.91 |
| aircraft_inspection | gpt-5-mini | mask | 112 | **75.9%** | 5.10 | 0.00 | 100% | 1,624,359 | $0.97 | 47.4s | 0.0001 | 0.91 |
| aircraft_inspection | gpt-5-mini | passive | 112 | **95.5%** | 6.28 | 0.00 | 100% | 2,282,394 | $1.37 | 29.7s | 0.0001 | 0.86 |
| aircraft_inspection | gpt-5-mini | baseline | 112 | **92.9%** | 6.41 | 0.00 | 92% | 2,326,867 | $1.40 | 35.5s | 0.0002 | 0.97 |
| warehouse_package_inspection | gpt-5-mini | acorn | 150 | **100.0%** | 3.90 | 0.20 | 100% | 1,224,399 | $0.73 | 32.5s | 0.0001 | 0.56 |
| warehouse_package_inspection | gpt-5-mini | mask | 150 | **51.3%** | 4.94 | 0.00 | 100% | 1,457,141 | $0.87 | 36.3s | 0.0001 | 0.55 |
| warehouse_package_inspection | gpt-5-mini | passive | 150 | **24.7%** | 6.23 | 0.00 | 100% | 2,883,986 | $1.73 | 39.1s | 0.0001 | 0.70 |
| warehouse_package_inspection | gpt-5-mini | baseline | 150 | **57.3%** | 5.61 | 0.00 | 16% | 2,445,146 | $1.47 | 30.2s | 0.0001 | 0.96 |
| email_intent | gpt-5-mini | acorn | 186 | **100.0%** | 1.65 | 0.38 | 100% | 717,016 | $0.43 | 12.6s | 0.0001 | 0.00 |
| email_intent | gpt-5-mini | mask | 186 | **93.5%** | 2.66 | 0.00 | 100% | 1,041,528 | $0.62 | 19.3s | 0.0001 | 0.00 |
| email_intent | gpt-5-mini | passive | 186 | **92.5%** | 4.64 | 0.00 | 100% | 1,991,279 | $1.19 | 22.5s | 0.0001 | 0.00 |
| email_intent | gpt-5-mini | baseline | 186 | **92.5%** | 4.60 | 0.00 | 99% | 1,994,241 | $1.20 | 21.9s | 0.0001 | 0.00 |
| content_flagging | gpt-5-mini | acorn | 168 | **100.0%** | 3.00 | 0.25 | 100% | 1,043,383 | $0.63 | 14.2s | 0.0002 | 0.53 |
| content_flagging | gpt-5-mini | mask | 168 | **98.2%** | 4.01 | 0.00 | 100% | 1,347,577 | $0.81 | 23.4s | 0.0001 | 0.53 |
| content_flagging | gpt-5-mini | passive | 168 | **100.0%** | 5.82 | 0.00 | 100% | 2,461,871 | $1.48 | 16.6s | 0.0001 | 0.54 |
| content_flagging | gpt-5-mini | baseline | 168 | **100.0%** | 5.81 | 0.00 | 100% | 2,459,212 | $1.48 | 15.9s | 0.0003 | 0.99 |
| video_annotation | gpt-5-mini | acorn | 125 | **100.0%** | 4.78 | 0.17 | 100% | 3,258,835 | $1.96 | 22.4s | 0.0002 | 0.18 |
| video_annotation | gpt-5-mini | mask | 125 | **88.8%** | 5.77 | 0.00 | 100% | 3,986,112 | $2.39 | 29.8s | 0.0002 | 0.18 |
| video_annotation | gpt-5-mini | passive | 125 | **92.0%** | 10.49 | 0.00 | 100% | 10,457,437 | $6.27 | 35.0s | 0.0002 | 0.18 |
| video_annotation | gpt-5-mini | baseline | 125 | **78.4%** | 9.79 | 0.00 | 72% | 9,667,553 | $5.80 | 30.5s | 0.0005 | 0.70 |
| video_classification | gpt-5-mini | acorn | 147 | **90.5%** | 4.12 | 0.18 | 100% | 1,312,287 | $0.79 | 21.3s | 0.0003 | 0.24 |
| video_classification | gpt-5-mini | mask | 147 | **60.5%** | 5.01 | 0.00 | 100% | 1,660,712 | $1.00 | 35.3s | 0.0001 | 0.24 |
| video_classification | gpt-5-mini | passive | 147 | **46.3%** | 10.27 | 0.00 | 100% | 5,363,850 | $3.22 | 33.4s | 0.0003 | 0.21 |
| video_classification | gpt-5-mini | baseline | 147 | **44.2%** | 10.22 | 0.00 | 56% | 5,287,296 | $3.17 | 29.4s | 0.0010 | 0.56 |

Macro-average across the 10 domains (gpt-5-mini): **acorn 94.5% vs
baseline 71.4%** TSR; acorn proc-clean 100% everywhere vs baseline
16–100%; acorn is the cheapest condition in 9/10 domains and the fastest
in 6/10.

### Domain notes (honest boundaries and mechanism attribution)

- **know_your_business** is the semantic-wall exhibit. The verification
  chain is fully bindable (sym ratio 0.89, exactly 1 model call/row) and
  the hard gates (TIN format, license >42d, sanctions/PEP/bank/registry
  flags) enforce with zero counterexamples — but the escalate-vs-awaiting
  verdict is a judgment call the SOP itself assigns to human experience.
  gpt-5-mini outputs "awaiting information" **0/34 times under every
  condition**, so the ~50–56% ceiling is model capability, condition-
  independent. acorn still wins on every axis: best TSR, 100% proc-clean
  (baseline commits 0.28 violations/row), 8× fewer calls, 4× faster,
  8.5× cheaper.
- **aircraft_inspection**: relay-style grading. mask *underperforms*
  baseline (75.9% vs 92.9%): with narrowed exposure the model batches
  calls into fewer turns and transcribes results from memory into the
  final report (e.g. rewriting an empty `aircraft_ready` as `FALSE`).
  Masking alone does not fix transcription; the binder does (99.1%).
  Counterpoint to patient_intake, where mask alone reaches 100%
  (+54.5pp) because that domain's failure mode is ordering, not relay.
- **warehouse_package_inspection**: passive **collapses below baseline**
  (24.7% vs 57.3%) — 335 block-and-reprompt events leave 27% of rows
  without a submitted report. Enforcement that only says "no" is worse
  than no enforcement; reshaping the action space (mask 51.3% with 100%
  proc-clean) and binding the computation (acorn 100%) is the fix.
  Baseline commits 1.59 violations/row (proc-clean 16%) — mostly the
  Wrong-Item "skip the damage assessment" prohibition.
- **video_annotation / video_classification** are the tool-exposure
  stress tests (26 and 25 tools, 20 of each being no-op distractors).
  Baseline wanders (≈10 calls/row, ECR 69–93%); mask alone is worth
  +10 to +16pp; acorn reaches 100% and 90.5%. The classification
  residue is honest: the Bullying-only moderation split depends on
  free-text moderator notes (binder abstains by design) and 2 rows are
  provably contradictory labels (pinned as noise in tests).
- **content_flagging / email_intent**: near-saturated domains; acorn's
  margin is efficiency (≈2–3× cheaper than baseline/passive at equal or
  better TSR).

## Cross-model (matched Bedrock lane, claude-4.5-haiku)

| domain | model | condition | n | TSR | calls/row | proc-clean | tokens | avg latency |
|---|---|---|---|---|---|---|---|---|
| customer_service | claude-4.5-haiku | acorn | 156 | **100.0%** | 5.19 | 100% | 2,581,274 | 30.7s |
| customer_service | claude-4.5-haiku | baseline | 156 | **52.6%** | 7.94 | 58% | 7,047,066 | 47.7s |
| patient_intake | claude-4.5-haiku | acorn | 66 | **100.0%** | 2.95 | 100% | 593,307 | 17.7s |
| patient_intake | claude-4.5-haiku | baseline | 66 | **89.4%** | 4.68 | 100% | 1,428,746 | 30.1s |
| dangerous_goods | claude-4.5-haiku | acorn | 274 | **100.0%** | 0.98 | 100% | 681,346 | – |
| dangerous_goods | claude-4.5-haiku | baseline | 274 | **86.5%** | 2.98 | 100% | 2,520,732 | 17.9s |
| dangerous_goods | gpt-oss-120b | acorn | 274 | **99.6%** | 3.98 | 100% | 1,539,293 | 6.9s |
| dangerous_goods | gpt-oss-120b | baseline | 274 | **73.0%** | 5.85 | 99% | 2,595,875 | 7.2s |
| dangerous_goods | llama-3.3-70b | acorn | 20 | **95.0%** | 4.20 | 100% | 143,468 | – |
| dangerous_goods | llama-3.3-70b | baseline | 20 | **0.0%** | 4.90 | 95% | 198,565 | 34.2s |

The weaker the base model, the larger the uplift, and the ceiling is
shared: Haiku baseline trails gpt-5-mini by 16pp on customer_service
(52.6% vs 68.6%) yet both reach 100% under acorn; Llama goes 0%→95%.

## Mask granularity spectrum (acorn condition, gpt-5-mini)

Billed-equivalent tokens = uncached + 0.1×cached (OpenAI cache discount).

### step vs phase, all 10 domains (clean runs, 0 error rows)

| domain | step TSR | phase TSR | step lat | phase lat | step billed | phase billed | Δbilled |
|---|---|---|---|---|---|---|---|
| dangerous_goods | 100.0% | 100.0% | – | 5.6s | 501k | 505k | +1% |
| customer_service | 100.0% | 100.0% | 31.5s | 14.2s | 970k | 818k | −16% |
| patient_intake | 100.0% | 100.0% | 32.0s | 22.8s | 542k | 313k | −42% |
| know_your_business | 55.6% | 55.6% | 8.8s | 6.6s | 303k | 307k | +1% |
| aircraft_inspection | 99.1% | 100.0% | 48.2s | 20.2s | 1170k | 628k | −46% |
| warehouse_package_inspection | 100.0% | 97.3% | 32.5s | 26.1s | 1223k | 861k | −30% |
| email_intent | 100.0% | 99.5% | 12.6s | 9.9s | 593k | 332k | −44% |
| content_flagging | 100.0% | 100.0% | 14.2s | 9.9s | 1043k | 511k | −51% |
| video_annotation | 100.0% | 100.0% | 22.4s | 13.0s | 997k | 708k | −29% |
| video_classification | 90.5% | 90.5% | 21.3s | 18.8s | 1149k | 966k | −16% |
| **total / macro** | **94.5%** | **94.3%** | | | **8.49M** | **5.95M** | **−30%** |

phase matches step on TSR (macro −0.2pp) at −30% billed tokens overall
(up to −51%) and up to 2.4× lower latency. The only non-saving domains
(dangerous_goods, know_your_business) are the fully-jumped ones —
≈1 model call per row leaves no cache to recover.

### Three granularities incl. hint (PI + CS)

| domain | granularity | TSR | avg latency | calls/row | billed tokens |
|---|---|---|---|---|---|
| patient_intake | step | **100.0%** | 32.0s | 3.7 | ≈541k |
| patient_intake | phase | **100.0%** | 22.8s | 4.0 | ≈313k |
| patient_intake | hint | 98.5% | 48.4s | 6.0 | ≈497k |
| customer_service | step | **100.0%** | 31.5s | 5.4 | ≈969k |
| customer_service | phase | **100.0%** | 14.2s | 5.4 | ≈818k |
| customer_service | hint | **100.0%** | 19.8s | 5.5 | ≈947k |

No dominance: step is the accuracy-safest (headline setting), phase is
the deployment default, hint is the fallback when tool schemas cannot be
touched (validate remains the hard boundary; 0 committed violations in
all settings).

## Run-to-run variance (gpt-5-mini)

acorn, 3 independent full-set runs per domain:

- **customer_service** (156 rows × 3): 100% / 100% / 100% — 100.0% ± 0.0pp
- **patient_intake** (66 rows × 3): 100% / 100% / 100% — 100.0% ± 0.0pp
- **warehouse_package_inspection** (150 rows × 3): 100% / 100% / 100% — 100.0% ± 0.0pp
- **dangerous_goods** (20 rows × 3): 100% / 100% / 100% — 100.0% ± 0.0pp

baseline (dangerous_goods, 20 rows × 3): 65% / 75% / 75% — 71.7% ± 5.8pp.
Symbolic control eliminates cross-run sampling variance at the ceiling;
baseline repeats retain ±5.8pp. Baseline single-run numbers for the other
domains are in the main matrix (per the no-rerun-of-referenced-data
policy, baselines were not repeated).

## τ²-bench retail (gpt-4.1-mini agent, gpt-4.1 user sim, 114 tasks × 4 trials)

Final matched-condition comparison. Both arms clean (≤3% infrastructure
errors, counted as failures). Full parity checklist applied to the acorn
arm before the final run: identical system prompt (official
`<instructions>` + `<policy>` template, imported), temperature 0.0,
litellm-equivalent retries, faithful tool schemas and message-role
rendering. Three earlier acorn runs under partial parity scored
pass^1 0.550/0.561/0.555 — the final number is stable, not tuned.

### Layer 1 — native pass^k (with the decomposition arm)

| arm | avg reward | pass^1 | pass^2 | pass^3 | pass^4 |
|---|---|---|---|---|---|
| official LLMAgent | 0.656 | **0.636** | 0.478 | 0.382 | 0.316 |
| shell (our protocol, EMPTY contract library) | 0.626 | 0.625 | 0.491 | 0.419 | **0.377** |
| acorn (contracts + obligations + mask) | 0.561 | 0.555 | 0.402 | 0.316 | 0.263 |

Causal decomposition: shell ≈ official on pass^1 (−1.1pp, within noise;
pass^4 actually HIGHER, 0.377 vs 0.316 — our protocol shell is more
consistent across trials than the litellm agent). The entire ~7pp
official-vs-acorn gap is therefore the price of the control
interventions under this 53-contract set, not harness infrastructure.
What that price buys is the Layer-3 result below.

### Layer 3 — procedure compliance (offline audit of the same saved
conversations; 53 honest contracts, evaluated condition-independently)

| arm | sims firing ≥1 violation | blind-spot (τ²-pass ∧ violating) | proc-clean^4 | joint^4 (pass ∧ clean) |
|---|---|---|---|---|
| official LLMAgent | 62.7% | **61.0%** | 12.3% | 7.9% |
| acorn | 26.8% | 23.3% | **64.9%** | **21.9%** |

- **61% of the official agent's "successful" conversations violate
  procedure** — native pass^k rewards non-compliant successes.
- Under the joint success-and-compliance criterion acorn is **2.8×**
  the official agent (21.9% vs 7.9%).
- acorn's residual violations are **100% in the `transition` category**
  — exactly the trace-mined conventions the two-tier design deliberately
  demotes to feedback-only enforcement; hard categories (`output_spec`
  etc.) are at **0.0%** vs official's 37.3%.
- Reference anchors (same offline audit, tau2's published runs):
  official gpt-4.1-mini scores joint^4 8.8%, gpt-4.1 28.9%,
  claude-3-7-sonnet 0.0%.

### Provenance-stratified audit (policy-grounded contracts only)

The 53-contract set mixes 17 contracts written from the policy text with
36 trace-mined "conventions" (transition_spec / predicted_plan). A mined
pattern that fires on 43.8% of the OFFICIAL agent's own passing traces
is not a rule (traces witness ∃; rules claim ∀). Restricting the audit
to the 17 policy-grounded contracts — immune to the "your contracts are
too tight" objection:

| arm (17 grounded contracts) | violation rate | blind spot | clean^4 | joint^4 |
|---|---|---|---|---|
| official LLMAgent | 37.3% | 35.9% | 19.3% | 8.8% |
| acorn | **0.0%** | **0.0%** | **100.0%** | **26.3%** |

acorn is PERFECTLY compliant on policy-grounded rules (joint^4 = its own
pass^4: every success is a compliant success), 3.0× the official agent.
An acorn arm enforcing only the 17 grounded contracts is running to
measure how much of the ~7pp enforcement price was mined-contract noise.

Framing: acorn trades ~8pp of native pass^1 for near-elimination of
committed procedure violations and a 2.8× joint success-and-compliance
rate — and the 61% blind-spot number is a critique of pass^k-only
evaluation, independent of our system.

### Baseline-parity checklist (methodology note)

Confounds found and eliminated while matching the official arm, each
worth carrying into any harness-vs-harness comparison: (1) system-prompt
framing (bare policy text vs the official instruction wrapper measurably
degrades the same model); (2) sampling temperature (unset = provider
default 1.0 vs official 0.0 — depresses pass^k through cross-trial
inconsistency); (3) retry policy under shared-key 429 windows; (4) tool
schema and message-role fidelity through the adapter.

_Estimated total model cost of all listed Amazon runs: ≈$65 (blended
per-Mtok estimates; exact billing lags in Cost Explorer)._

## Expressiveness census: what tool-list partitioning can and cannot say

Across all 10 Amazon domain libraries (170 deterministic constraints),
classified by what a workflow-graph medium (states + per-state tool
lists, LangGraph-style) can express declaratively:

| constraint class | count | share | partition-expressible? |
|---|---|---|---|
| ordering (A before B) | 54 | 32% | yes — state sequencing |
| counting (at_most N) | 113 | 66% | only via product states (2^k blowup; video_annotation alone needs 2^27) |
| argument-level (same tool, some argument values forbidden) | 1 (+3 in τ² grounded set) | ~1% | no — tool lists cannot see arguments |
| liveness/obligations ("eventually X"; 10 derived in τ²) | — | — | no — hiding other tools cannot force an action |

Only ~1/3 of real SOP constraints are declaratively expressible by
tool-list partitioning. The rest must either explode the graph or sink
into imperative node code — losing certificates (SAT/conflict checks),
condition-independent auditability, portability, and composability.
ACORN keeps all 170 as declarative, verifiable first-class objects at
O(n) representation cost. (Practice anchor: published LangGraph
tutorials and production case studies use 4–30 nodes — the faithful
product machine for video_annotation alone would need ≥10^9 states.)
