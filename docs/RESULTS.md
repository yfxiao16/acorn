# ACORN × Amazon SOP-Bench — overnight results (2026-08-20)

Model-matched four-condition ablation. All graded against the packs'
labeled dev sets; compliance audited by the same contract library in
observe mode across every condition.

| domain | model | condition | n | TSR | calls/row | sym ratio | proc-clean | tokens | est. cost | avg latency | ctrl share | state reuse |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dangerous_goods | gpt-5-mini | acorn | 274 | **100.0%** | 0.99 | 0.50 | 100% | 501,018 | $0.30 | – | – | – |
| dangerous_goods | gpt-5-mini | baseline | 274 | **84.7%** | 2.98 | 0.00 | 100% | 1,671,981 | $1.00 | – | – | – |
| dangerous_goods | gpt-5-mini | passive | 274 | **85.4%** | 2.99 | 0.00 | 100% | 1,658,938 | $1.00 | 16.8s | 0.0001 | 0.91 |
| dangerous_goods | gpt-5-mini | mask | 274 | **81.8%** | 1.99 | 0.00 | 100% | 992,265 | $0.60 | 14.4s | 0.0002 | 0.93 |
| dangerous_goods | claude-4.5-haiku | acorn | 274 | **100.0%** | 0.98 | 0.50 | 100% | 681,346 | $1.23 | – | – | – |
| dangerous_goods | claude-4.5-haiku | baseline | 274 | **86.5%** | 2.98 | 0.00 | 100% | 2,520,732 | $4.54 | 17.9s | 0.0001 | 0.99 |
| dangerous_goods | gpt-oss-120b | acorn | 274 | **99.6%** | 3.98 | 0.20 | 100% | 1,539,293 | $0.46 | 6.9s | 0.0009 | 0.94 |
| dangerous_goods | gpt-oss-120b | baseline | 274 | **73.0%** | 5.85 | 0.00 | 99% | 2,595,875 | $0.78 | 7.2s | 0.0005 | 0.99 |
| dangerous_goods | llama-3.3-70b | acorn | 20 | **95.0%** | 4.20 | 0.18 | 100% | 143,468 | $0.13 | – | – | – |
| dangerous_goods | llama-3.3-70b | baseline | 20 | **0.0%** | 4.90 | 0.00 | 95% | 198,565 | $0.18 | 34.2s | 0.0001 | 0.90 |
| customer_service | gpt-5-mini | acorn | 156 | **100.0%** | 5.44 | 0.16 | 100% | 2,162,452 | $1.30 | 31.5s | 0.0003 | 0.48 |
| customer_service | gpt-5-mini | baseline | 156 | **68.6%** | 7.28 | 0.00 | 73% | 4,023,794 | $2.41 | 25.9s | 0.0003 | 0.97 |
| customer_service | gpt-5-mini | mask | 156 | **69.9%** | 6.39 | 0.00 | 100% | 2,727,985 | $1.64 | 62.0s | 0.0001 | 0.47 |
| customer_service | gpt-5-mini | passive | 156 | **69.9%** | 7.39 | 0.00 | 100% | 4,166,792 | $2.50 | 33.4s | 0.0001 | 0.46 |
| patient_intake | gpt-5-mini | baseline | 66 | **45.5%** | 2.94 | 0.00 | 98% | 539,312 | $0.32 | 21.9s | 0.0001 | 0.93 |
| patient_intake | gpt-5-mini | passive | 66 | **43.9%** | 2.89 | 0.00 | 100% | 523,012 | $0.31 | 20.3s | 0.0001 | 0.85 |
| patient_intake | gpt-5-mini | mask | 66 | **100.0%** | 4.73 | 0.00 | 100% | 726,955 | $0.44 | 38.0s | 0.0002 | 0.90 |
| patient_intake | gpt-5-mini | acorn | 66 | **100.0%** | 3.73 | 0.21 | 100% | 605,381 | $0.36 | 32.0s | 0.0003 | 0.90 |

## Run-to-run variance (dangerous_goods, gpt-5-mini, 20 rows × 3 trials)

- **acorn**: ['100%', '100%', '100%'] — mean 100.0% ± 0.0pp
- **base**: ['65%', '75%', '75%'] — mean 71.7% ± 5.8pp

_Estimated total model cost of all listed runs: $19.49 (blended per-Mtok estimates; exact billing lags 24h in Cost Explorer)._
