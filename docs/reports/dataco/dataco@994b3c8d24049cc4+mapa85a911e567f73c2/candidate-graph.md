# Candidate Graph Report

> **BOUNDED RUN.** Built from the first 150 rows of the clean
> layer, not from all 180,519. Module 9 is not a streaming
> module -- the two counting generators measure across process instances and
> the confounder walk needs the graph in hand -- and the full expansion does
> not fit in memory as models on an 8 GB machine
> (`tests/integration/test_full_expansion_budget.py`). **Every number below
> measures this slice, not the dataset.** Re-run with `--rows 0` to remove
> the bound.

- `report_schema_version`: `1.1.0`
- `run_id`: `run:f5e7ab410fa9eeb4`
- events examined: 1224
- process instances (timelines) examined: 733
- candidates retained: 17864

This module proposes hypotheses. It assigns no confidence, performs no ranking,
and prunes nothing on plausibility. Every number below is a count.

## Generators that could not run

These did **not** run. That is not the same as running and finding nothing,
and it is reported separately for exactly that reason.

- **`shared_identifier`** needs: candidate_generation.identifier_metadata_keys -- which Event.metadata keys carry a domain identifier rather than the Event Generator's traceability pairs -- and candidate_generation.shared_identifier_strength. Declaring no keys switches this generator off deliberately: on a dataset whose every identifier becomes a participant entity, there is nothing here the shared-entity generator does not already reach.

## Generators whose output looks degenerate

- **`structural_path`** ran and proposed nothing while other generators proposed. Either its declared parameters admit no pair in this data, or it has a pairing defect.

## Candidates by generator

| generator | status | proposed | merged | admitted | retained | available pairs |
|---|---|---:|---:|---:|---:|---:|
| `historical_frequency` | RAN | 35422 | 5325 | 30097 | 4370 | 100304 |
| `rule_based` | RAN | 20325 | 0 | 20325 | 2297 | 100304 |
| `shared_entity` | RAN | 87446 | 0 | 78140 | 6588 | 100304 |
| `shared_identifier` | NOT_RUNNABLE | 0 | 0 | 0 | 0 | 100304 |
| `statistical_association` | RAN | 27101 | 4447 | 22654 | 4126 | 100304 |
| `structural_path` | RAN | 0 | 0 | 0 | 0 | 100304 |
| `temporal_proximity` | RAN | 1083 | 596 | 483 | 483 | 100304 |

`merged` counts proposals folded into another making the identical claim -- same
pair, same generator, same payload -- with their evidence carried across. A large
value means the pack justifies few hypotheses many ways, not that candidates were
lost: `proposed == merged + admitted + rejected`.

## Rejections per effect event

**143,145 claim(s) were refused across 955 effect event(s)**, worst first. Each row is one outcome nothing was kept against, or was nearly not kept against. Read it beside the retained counts above: an effect near the top of this table and absent from the graph was not overlooked, it was considered and refused, and the reasons are on the graph's own rejection records.

| effect | claims refused |
|---|---:|
| `evt:f8e0f74d1d695a14` | 567 |
| `evt:b5452a7017a4a3f6` | 515 |
| `evt:9fc2541dc5289133` | 505 |
| `evt:e92168a1a53a6df6` | 500 |
| `evt:ef3c2a66b39064c6` | 481 |
| `evt:fd155a0327b5b9ae` | 475 |
| `evt:62e09c13f5ddfbeb` | 469 |
| `evt:cb36d8bd468068ae` | 449 |
| `evt:eca7a466b32fc7aa` | 444 |
| `evt:eebca1335b414b8f` | 444 |
| `evt:3755a09fb2fcbab4` | 441 |
| `evt:2d51ecdb6aa920dc` | 437 |
| `evt:c1f0efa57b16ee49` | 437 |
| `evt:b63b372000a4faf6` | 434 |
| `evt:c36c4fed1e0b5251` | 430 |
| `evt:ef593bd95b2764f5` | 430 |
| `evt:b044c7008d8da7d3` | 427 |
| `evt:ff5206e27778879b` | 426 |
| `evt:1cac6b7971275680` | 425 |
| `evt:78f287579e539379` | 422 |
| `evt:ca4b613ed2c63379` | 418 |
| `evt:6bcdba6f7c2a5fe9` | 416 |
| `evt:81c2390ff8961ff9` | 416 |
| `evt:935b3b6a8d641445` | 416 |
| `evt:0bc18deba779af6a` | 413 |
| `evt:65ba4673a44b3970` | 408 |
| `evt:765dbf2534f0acc8` | 408 |
| `evt:e4033d71aa6f35c0` | 404 |
| `evt:595f3ecd7cc76c3f` | 403 |
| `evt:bca13c2e6aea1b9f` | 399 |
| `evt:e6e94350860b1ce5` | 398 |
| `evt:ca5a51aeb30fe7b5` | 396 |
| `evt:b2598bb371622f80` | 392 |
| `evt:e64fb949340e784e` | 392 |
| `evt:bf10bbb63744be90` | 391 |
| `evt:77467075775cd31d` | 390 |
| `evt:af010317d159eb5e` | 387 |
| `evt:25d2d7a1fa8848b7` | 378 |
| `evt:736fc8712a3c6276` | 378 |
| `evt:9a3e46447dc4e9c4` | 377 |

915 further effect(s) are not printed here, accounting for 126,007 more refusal(s). The counts above are complete; only this rendering is bounded.

A refusal is not a judgement about the outcome. Three of the reasons are properties of the DATA -- precedence that could not be established, a pair the pack prohibits -- and one, the per-effect cap, is a bound this run declared on itself. An effect whose refusals are mostly capped ones had more hypotheses than the cap admits, which is a different finding from one with none.

## Rejections by reason

| generator | temporal violation | self edge | constraint | truncated by cap | not runnable |
|---|---:|---:|---:|---:|---:|
| `historical_frequency` | 0 | 0 | 0 | 25727 | 0 |
| `rule_based` | 0 | 0 | 0 | 18028 | 0 |
| `shared_entity` | 9306 | 0 | 0 | 71552 | 0 |
| `shared_identifier` | 0 | 0 | 0 | 0 | 1 |
| `statistical_association` | 0 | 0 | 0 | 18528 | 0 |
| `structural_path` | 0 | 0 | 0 | 0 | 0 |
| `temporal_proximity` | 4 | 0 | 0 | 0 | 0 |
| **total** | 9310 | 0 | 0 | 133835 | 1 |

A large `temporal violation` count is a finding about the declared windows.
A large `constraint` count is a finding about the rule pack.

## Candidates per effect event

- effects holding at least one candidate: 1224
- minimum: 2 · median: 20 · maximum: 20

| candidates per effect (up to) | effects |
|---:|---:|
| 1 | 0 |
| 2 | 37 |
| 5 | 113 |
| 10 | 265 |
| 20 | 809 |

## Temporal standing

Two counts, never summed. They are different findings about the dataset
(`docs/contracts.md` §3).

- **`UNDETERMINED`**: 2587 (0.144816 of retained). The data placed both events and could not separate them.
- **temporally unverifiable**: 15023 (0.840965 of retained). The data never placed one of them.
- **promotable to `INFERRED`**: 254. Neither of the above; LAW-TIME does not block promotion. Whether any of them IS promoted is module 10's decision, not this module's.

A dominant `UNDETERMINED` share is a finding about the source's granularity
(`CONTEXT.md` R-14). It is never resolved by loosening the test.

## Truncation

657 effect event(s) exceeded the cap; 133835 candidate(s) were truncated. Selection is round-robin across generators in canonical sequence -- fair allocation, never a plausibility ranking.


| effect | cap | proposed | retained | dropped by generator |
|---|---:|---:|---:|---|
| `evt:005ed1068f0114b5` | 20 | 314 | 20 | `rule_based`: 114, `shared_entity`: 180 |
| `evt:007d411e04707d0d` | 20 | 249 | 20 | `rule_based`: 56, `shared_entity`: 173 |
| `evt:011e09ab5b22f677` | 20 | 293 | 20 | `rule_based`: 52, `shared_entity`: 221 |
| `evt:0137f38df71a4f99` | 20 | 94 | 20 | `rule_based`: 3, `shared_entity`: 71 |
| `evt:015bd166df4b2162` | 20 | 109 | 20 | `historical_frequency`: 28, `rule_based`: 8, `shared_entity`: 28, `statistical_association`: 25 |
| `evt:01b425e0433ae8fd` | 20 | 71 | 20 | `historical_frequency`: 18, `shared_entity`: 23, `statistical_association`: 10 |
| `evt:01f6474ec2cc5f7d` | 20 | 250 | 20 | `rule_based`: 56, `shared_entity`: 174 |
| `evt:01f71362c7117689` | 20 | 164 | 20 | `historical_frequency`: 47, `rule_based`: 8, `shared_entity`: 62, `statistical_association`: 27 |
| `evt:026c7de118d1369d` | 20 | 337 | 20 | `rule_based`: 122, `shared_entity`: 195 |
| `evt:030faa42579953be` | 20 | 69 | 20 | `historical_frequency`: 15, `shared_entity`: 19, `statistical_association`: 15 |
| `evt:0334d401b2de1c02` | 20 | 271 | 20 | `rule_based`: 57, `shared_entity`: 194 |
| `evt:035729f316c8b0dd` | 20 | 263 | 20 | `rule_based`: 52, `shared_entity`: 191 |
| `evt:0392cc05df7c7b20` | 20 | 355 | 20 | `historical_frequency`: 110, `shared_entity`: 170, `statistical_association`: 55 |
| `evt:03b255f72b937bc4` | 20 | 28 | 20 | `historical_frequency`: 3, `shared_entity`: 5 |
| `evt:03ecf39fdd4cb033` | 20 | 66 | 20 | `historical_frequency`: 15, `shared_entity`: 15, `statistical_association`: 16 |
| `evt:044bb13e02bd02c9` | 20 | 333 | 20 | `historical_frequency`: 114, `shared_entity`: 140, `statistical_association`: 59 |
| `evt:049e5f35718fc67d` | 20 | 346 | 20 | `rule_based`: 57, `shared_entity`: 269 |
| `evt:052bbac170fd2219` | 20 | 209 | 20 | `historical_frequency`: 46, `shared_entity`: 97, `statistical_association`: 46 |
| `evt:05a67daa8fbd2beb` | 20 | 33 | 20 | `historical_frequency`: 4, `shared_entity`: 4, `statistical_association`: 5 |
| `evt:063f1825c66927f4` | 20 | 281 | 20 | `historical_frequency`: 84, `shared_entity`: 120, `statistical_association`: 57 |
| `evt:07050b4de7e2d397` | 20 | 254 | 20 | `rule_based`: 52, `shared_entity`: 182 |
| `evt:076746e26240751e` | 20 | 131 | 20 | `rule_based`: 27, `shared_entity`: 84 |
| `evt:07881d792b64403d` | 20 | 179 | 20 | `historical_frequency`: 46, `shared_entity`: 67, `statistical_association`: 46 |
| `evt:079f0345da500755` | 20 | 115 | 20 | `historical_frequency`: 22, `shared_entity`: 50, `statistical_association`: 23 |
| `evt:07bb14b4a07275bc` | 20 | 101 | 20 | `rule_based`: 24, `shared_entity`: 57 |
| `evt:07e2ae946b163ef0` | 20 | 51 | 20 | `historical_frequency`: 10, `shared_entity`: 14, `statistical_association`: 7 |
| `evt:0809a95d778b18b0` | 20 | 27 | 20 | `historical_frequency`: 3, `shared_entity`: 4 |
| `evt:080ecd9ca463d41e` | 20 | 69 | 20 | `historical_frequency`: 19, `shared_entity`: 20, `statistical_association`: 10 |
| `evt:083a0bed819867a4` | 20 | 113 | 20 | `historical_frequency`: 23, `shared_entity`: 46, `statistical_association`: 24 |
| `evt:084d9e3505fa4c2c` | 20 | 110 | 20 | `historical_frequency`: 33, `rule_based`: 4, `shared_entity`: 36, `statistical_association`: 17 |
| `evt:08ff1f631be0ee08` | 20 | 261 | 20 | `rule_based`: 53, `shared_entity`: 188 |
| `evt:097fcba85bb89333` | 20 | 295 | 20 | `historical_frequency`: 82, `shared_entity`: 137, `statistical_association`: 56 |
| `evt:09943dde645ccdef` | 20 | 164 | 20 | `historical_frequency`: 47, `rule_based`: 5, `shared_entity`: 66, `statistical_association`: 26 |
| `evt:09ed325eb7ce6736` | 20 | 340 | 20 | `rule_based`: 124, `shared_entity`: 196 |
| `evt:0a8cc6602ef4cf45` | 20 | 100 | 20 | `historical_frequency`: 26, `rule_based`: 5, `shared_entity`: 31, `statistical_association`: 18 |
| `evt:0abbd2e98bb18c61` | 20 | 313 | 20 | `historical_frequency`: 111, `shared_entity`: 127, `statistical_association`: 55 |
| `evt:0bc18deba779af6a` | 20 | 433 | 20 | `rule_based`: 141, `shared_entity`: 272 |
| `evt:0c7d749ef7153e5b` | 20 | 99 | 20 | `historical_frequency`: 27, `shared_entity`: 40, `statistical_association`: 12 |
| `evt:0ccd04ce772142ec` | 20 | 302 | 20 | `historical_frequency`: 85, `shared_entity`: 138, `statistical_association`: 59 |
| `evt:0d3a13d87bd92fc4` | 20 | 103 | 20 | `historical_frequency`: 27, `rule_based`: 5, `shared_entity`: 33, `statistical_association`: 18 |

617 further truncated effect(s) are not printed here, losing 126940 candidate(s) between them. **They are not omitted from the report** -- `candidate-graph.json` beside this file carries every record. Only the rendering is bounded, and it says so, because an unstated cut reads as a complete list.

## Confounding structures made visible

- `POSSIBLE_COMMON_CAUSE`: 34290
- `POSSIBLE_MEDIATION`: 34290
- **total**: 68580

This flag makes a structure visible; it does not resolve it. Nothing in V1 distinguishes a direct effect from one explained by the third event, and the absence of a flag is not evidence of no confounding -- an unobserved common cause leaves no shape in a graph built from observed events (prd.md §59, CONTEXT.md R-05).

**Density note.** There are 3.84 flags per retained candidate. At that rate nearly every candidate sits in some triangle, and a flag stops distinguishing anything -- it is a property of a dense graph rather than a finding about particular claims. Read it as a statement about this graph's shape, and expect the per-effect cap and the pack's declared windows to govern it more than the data does.

The report carries 50 flag(s) as a sample; all 68580 are returned on `GenerationResult.confounding_flags` for module 10. The bound is on this document, not on the detection.
