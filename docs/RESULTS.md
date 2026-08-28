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
| shell (our protocol, EMPTY contract library) | 0.626 | 0.625 | 0.491 | 0.419 | 0.377 |
| **acorn, 17 grounded contracts** | 0.637 | **0.634** | 0.509 | 0.443 | **0.395** |
| acorn, full 53 contracts | 0.561 | 0.555 | 0.402 | 0.316 | 0.263 |

**Headline: enforcing the policy's actual rules is free.** The grounded
arm ties official pass^1 (63.4 vs 63.6), posts the best pass^4 of any
arm (39.5), and audits perfectly clean (joint^4 = its own pass^4 =
39.5, 4.5× official's 8.8). The full-53 arm's −7.9pp is the price of
enforcing mined pseudo-rules — contract quality, not enforcement, is
the price driver. Attribution note: the shell also audits clean on the
grounded ruler (official's grounded violations are protocol-family,
which our agent interface prevents structurally); the contract layer
upgrades that empirical cleanliness to a guarantee.

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

## Workflow↔agent sweep (enforcement-medium transfer, claude-4.5-haiku)

Each movable constraint enforced exactly once — either as external
contract (restrictive: prune violations only) or internalized flow
structure (prescriptive: stage-machine). Full-library observe auditor
throughout (medium-independent accounting). freedom = mean exposed
actions per neural decision.

### KYB — linear regime (6 orderings, 5 cuts, 90 rows/profile)

| profile | freedom | TSR | proc-clean | sym steps/row | latency |
|---|---|---|---|---|---|
| x0 (all-external) | 2.66 | 50.0% | 100% | 1.0 | 20.2s |
| x1 | 2.32 | 51.1% | 100% | 2.1 | 18.2s |
| x2 | 2.00 | 54.4% | 100% | 2.8 | 20.7s |
| x3 | 1.99 | 52.2% | 100% | 3.3 | 18.2s |
| x4 | 1.99 | 52.2% | 100% | 3.5 | 18.2s |
| x5 (all-internal) | 2.00 | 54.4% | 100% | 3.5 | 18.0s |

Quality flat within noise; compliance invariant; internalization buys
modest efficiency (more singleton stages → more jumps). Media are
interchangeable for simple sequential procedure.

### WH — branching regime (150 rows/profile, clean reruns, 0 error rows)

| profile | TSR | proc-clean | viol/row | Wrong-Item viol |
|---|---|---|---|---|
| free (all-external, no flow) | 94.0% | 100% | 0 | 0 |
| flat (external + trivial shell) | 99.3% | 100% | 0 | 0 |
| branch (correct internalization) | 100% | 100% | 0 | 0 |
| naive (branch-blind internalization, no external net) | 100% | **64%** | **1.08** | **3.00** |

naive's damage is invisible to outcome metrics (TSR 100% — the fact
layer rescues outputs) and fully visible to the audit. free's 94% is
completion discipline (prose instead of submit; fixable with an
eventually-submit obligation).

### VA — wide-tool regime (26 tools, 20 distractors, 125 rows/profile)

| profile | freedom | TSR | proc-clean | calls/row | latency |
|---|---|---|---|---|---|
| free (all-external) | 10.02 | 86.4% | 99% | 11.75 | 70s |
| phases (coarse internalization) | 1.58 | 100% | **88%** | 4.38 | 68s |
| pipeline (full internalization) | 1.00 | 100% | 100% | 4.86 | 116s |

Two mechanisms: (1) **contracts forbid the illegal; exposure removes
the useless** — calling a distractor violates nothing, so external
enforcement alone cannot fix distraction (11.75 calls/row, −13.6pp);
attention needs prescriptive scoping. (2) Coarse internalization
under-enforces: phases dropped the intra-stage orderings it claimed to
internalize (2-tool stages don't order their members) — audit catches
12% of rows; enforce-exactly-once bookkeeping must be exact.

## Matched-model matrix (Bedrock lane, step masking, complete columns)

Same contract libraries, unchanged, across model families. proc-clean is
audited by the full library in observe mode in every cell.

| domain | model | n | base TSR | acorn TSR | base clean | acorn clean | base calls | acorn calls |
|---|---|---|---|---|---|---|---|---|
| dangerous_goods | oss | 274 | 73.4% | **100.0%** | 99% | **100%** | 5.84 | 3.97 |
| customer_service | oss | 156 | 69.9% | **92.9%** | 69% | **100%** | 7.18 | 6.05 |
| patient_intake | oss | 66 | 97.0% | **100.0%** | 97% | **100%** | 7.83 | 6.02 |
| know_your_business | oss | 90 | 56.7% | **56.7%** | 20% | **100%** | 8.64 | 1.00 |
| aircraft_inspection | oss | 112 | 29.5% | **81.2%** | 25% | **100%** | 6.07 | 8.38 |
| warehouse_package_inspection | oss | 150 | 40.0% | **96.0%** | 11% | **99%** | 4.67 | 6.59 |
| email_intent | oss | 186 | 95.7% | **98.4%** | 77% | **100%** | 4.02 | 2.13 |
| content_flagging | oss | 168 | 95.8% | **98.2%** | 93% | **100%** | 5.92 | 4.64 |
| video_annotation | oss | 125 | 57.6% | **84.0%** | 54% | **98%** | 5.38 | 4.97 |
| video_classification | oss | 147 | 42.2% | **89.1%** | 12% | **100%** | 7.20 | 4.27 |
| **macro (gpt-oss-120b)** | | | **65.8%** | **89.7%** | | | | |
| dangerous_goods | llama | 274 | 0.0% | **100.0%** | 98% | **100%** | 4.93 | 3.93 |
| customer_service | llama | 156 | 20.5% | **86.5%** | 29% | **100%** | 8.54 | 7.48 |
| patient_intake | llama | 66 | 77.3% | **100.0%** | 50% | **100%** | 5.00 | 6.03 |
| know_your_business | llama | 90 | 38.9% | **52.2%** | 19% | **99%** | 5.04 | 1.06 |
| aircraft_inspection | llama | 112 | 1.8% | **99.1%** | 0% | **99%** | 2.43 | 6.99 |
| warehouse_package_inspection | llama | 150 | 31.3% | **100.0%** | 6% | **100%** | 6.85 | 5.87 |
| email_intent | llama | 186 | 91.9% | 81.7% | 74% | **100%** | 4.00 | 3.93 |
| content_flagging | llama | 168 | 100.0% | **100.0%** | 96% | **100%** | 6.06 | 4.00 |
| video_annotation | llama | 125 | 71.2% | **100.0%** | 0% | **100%** | 2.22 | 4.71 |
| video_classification | llama | 147 | 10.2% | **86.4%** | 0% | **100%** | 2.00 | 5.31 |
| **macro (llama-3.3-70b)** | | | **44.3%** | **90.6%** | | | | |

### claude-4.5-haiku column (complete, 20/20 — the model used for every sweep experiment)

| dangerous_goods | claude-4.5-haiku | 274 | 81.8% | **100.0%** | 99% | **100%** | 2.99 | 0.98 |
| customer_service | claude-4.5-haiku | 156 | 51.3% | **100.0%** | 62% | **100%** | 7.94 | 5.18 |
| patient_intake | claude-4.5-haiku | 66 | 92.4% | **100.0%** | 100% | **100%** | 4.73 | 3.05 |
| know_your_business | claude-4.5-haiku | 90 | 50.0% | **58.9%** | 94% | **100%** | 4.61 | 1.03 |
| aircraft_inspection | claude-4.5-haiku | 112 | 87.5% | **98.2%** | 97% | **100%** | 5.02 | 3.64 |
| warehouse_package_inspection | claude-4.5-haiku | 150 | 49.3% | **98.7%** | 49% | **100%** | 4.62 | 3.48 |
| email_intent | claude-4.5-haiku | 186 | 96.2% | **98.4%** | 100% | **100%** | 3.03 | 1.01 |
| content_flagging | claude-4.5-haiku | 168 | 100.0% | **100.0%** | 100% | **100%** | 5.14 | 3.01 |
| video_annotation | claude-4.5-haiku | 125 | 84.0% | **100.0%** | 74% | **86%** | 9.60 | 4.34 |
| video_classification | claude-4.5-haiku | 147 | 55.8% | **87.1%** | 50% | **100%** | 7.71 | 6.34 |
| **macro (claude-4.5-haiku, 10/10 domains)** | | | **74.8%** | **94.1%** | | | | |

Haiku macro: **74.8% → 94.1%** (+19.3pp). Baseline proc-clean collapses on
the same domains as for the other families (warehouse 49%, video_classification
50%, customer_service 62%) and acorn restores 100% on all but video_annotation
(86% — the wide-tool domain where the step mask still lets a few
out-of-stage calls through before the fact layer catches up; TSR is 100%).
video_classification acorn carries a 9/147 max_steps cluster (6%; below the
damage threshold, reported as-is). Four complete columns now agree:
acorn macro 89.7–94.5% for every family against baselines of 44–75%.

### What the complete columns add

1. **Uplift scales inversely with base capability, ceiling is shared.**
   Llama +46.3pp (44.3→90.6), gpt-oss +23.9pp (65.8→89.7), gpt-5-mini
   +23.1pp (71.4→94.5). The acorn macro sits in 89.7–94.5% for every
   family despite baselines spanning 44–71%.
2. **Baseline compliance collapses for weaker models — and the harness
   restores it exactly.** Llama's baseline proc-clean is 0% on three
   domains (aircraft, video_annotation, video_classification) and 6% on
   warehouse; gpt-oss is at 11–25% on its hard domains. Under acorn every
   cell is 98–100%. Procedural competence is what a weaker model lacks
   first, and it is precisely what the contract layer supplies.
3. **The semantic wall is model-invariant.** know_your_business shows no
   TSR gain for gpt-oss (56.7→56.7) and a partial one for Llama
   (38.9→52.2) — while its proc-clean goes 20%→100% and 19%→99%. The
   ceiling is a property of the task's judgment content, not of the
   harness or the model tier.
4. **Honest negative: llama/email_intent inverts (91.9→81.7).** 26 of 34
   acorn failures hit max_steps without submitting: the intent-recording
   tool has a strict enum schema, and this model repeatedly proposed
   invalid enum values until the step budget ran out, whereas the
   baseline's free-text path parses loosely. Strict recording protocols
   tax weak instruction-followers; we report it rather than relaxing the
   schema to recover the points.

## ReAct scaffold comparison (claude-4.5-haiku, step masking)

The benchmark's own paper reports both a function-calling (FC) agent and
a ReAct agent; our `--scaffold react` wrapper implements the classic
Thought/Action/Observation text protocol around the same model, tools
and prompts. Fairness audit: ReAct answers that never reached
submit_result were re-parsed with a lenient tag/key-value parser across
all saved runs — at most 1 row in 93 cells changes, so the comparison is
not a parsing artifact.

| domain | FC base | ReAct base | acorn | FC clean | ReAct clean | acorn clean |
|---|---|---|---|---|---|---|
| dangerous_goods | 81.8 | 77.4 | **100.0** | 99 | 98 | **100** |
| customer_service | (rebuild) | 67.3 | **100.0** | – | 96 | **100** |
| patient_intake | 92.4 | 98.5 | **100.0** | 100 | 100 | **100** |
| know_your_business | (rebuild) | 47.8 | **58.9** | – | 93 | **100** |
| aircraft_inspection | 87.5 | 92.0 | **98.2** | 97 | 100 | **100** |
| warehouse_package_inspection | 49.3 | **18.0** | **98.7** | 49 | 59 | **100** |
| email_intent | 96.2 | 95.2 | **98.4** | 100 | **92** | **100** |
| content_flagging | (rebuild) | 98.2 | **100.0** | – | 100 | **100** |
| video_annotation | (rebuild) | 84.0 | (rebuild) | – | **78** | – |
| video_classification | (rebuild) | 53.7 | **87.1** | – | 89 | **100** |
| **macro (9 shared domains)** | | **72.0** | **93.5** | | 90.5 | **100** |

Findings:

1. **A stronger neural scaffold does not buy compliance.** ReAct's
   proc-clean is 59–100% by domain (macro 90.5%); acorn is 100%
   everywhere. Swapping the reasoning scaffold is not a substitute for
   an enforcement layer.
2. **ReAct is not uniformly better than FC either**: it helps
   aircraft (+4.5pp) and patient_intake (+6.1pp) but collapses on the
   branching warehouse domain (18.0% vs FC's 49.3%) — 95 of its 123
   failures there are submitted-but-wrong (chargeback/classification
   reasoning errors), plus single-call hallucinated "completion
   reports". Scaffold quality is regime-dependent, echoing the sweep.
3. **Orthogonality (ReAct + acorn combo arms):** the contract layer
   composes with the scaffold and lifts it to the ceiling —
   dangerous_goods 77.4→**100.0** (viol 0.08→0), customer_service
   67.3→**98.1** (viol 0.04→0), patient_intake 98.5→**100.0**. ACORN is
   not a competitor to neural strategies; it is a compliance layer on
   top of any of them.
