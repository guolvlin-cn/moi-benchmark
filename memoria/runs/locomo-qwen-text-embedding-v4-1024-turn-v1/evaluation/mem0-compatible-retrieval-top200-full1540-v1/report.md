# LoCoMo Memoria Retrieval-only report

- Status: **COMPLETE**
- Selected questions: 1540
- Evidence-evaluable questions: 1536
- Valid retrievals: 1540/1540
- Client latency P50/P95: 799.1 / 2032.4 ms

## Strict evidence metrics

Failed or invalid retrievals are retained in the denominator and score zero.

| Metric | @10 | @20 | @50 | @200 |
| --- | ---: | ---: | ---: | ---: |
| Hit accuracy | 11.26% (173/1536) | 21.94% (337/1536) | 48.05% (738/1536) | 87.57% (1345/1536) |
| Mean evidence recall | 9.46% | 18.94% | 42.49% | 81.62% |
| Complete recall | 8.33% (128/1536) | 16.86% (259/1536) | 38.61% (593/1536) | 75.00% (1152/1536) |

MRR@200: 0.0577

## By category

| Category | N | Hit@10 | Hit@20 | Hit@50 | Hit@200 | Complete@200 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| multi-hop | 282 | 11.70% | 20.21% | 45.39% | 86.17% | 35.11% |
| open-domain | 92 | 10.87% | 14.13% | 27.17% | 73.91% | 47.83% |
| single-hop | 841 | 11.42% | 22.47% | 49.35% | 87.87% | 86.68% |
| temporal | 321 | 10.59% | 24.30% | 52.96% | 91.90% | 87.23% |

## Retrieval paths

- hybrid: 1540
