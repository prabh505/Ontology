# HANDOFF.md — Transfer protocol

For any new AI session, any new model, or any new human taking over Project CausaLog.

**Governing rule, stated once and applied everywhere below:**

> **Code is the truth about what IS. Docs are the truth about what SHOULD BE.**
> When they disagree, that is a **defect**, not a documentation chore. It is filed,
> classified, and resolved — never silently edited away.

---

## 1. Reading order

Do this before accepting any task. Do not skip, do not skim, do not start with the PRD.

```
Read CONTEXT.md, DECISIONS.md, PROGRESS.md, and CONVENTIONS.md in full.
Then read docs/architecture.md, and the docs/prd.md sections relevant to the
task I am about to give you.
Summarize in <=10 bullets: current phase, last completed module, open risks,
and any constraint that applies to today's task. Do not write code yet.
```

*(The PRD moved to `docs/prd.md` — ADR-0017 closed OQ-010. `docs/architecture.md` is the
truth about structure: layer ranks, forbidden edges, the storage boundary, and the Run
model. Read it before touching any module boundary.)*

Expanded order, with what each file answers and what it costs you to skip:

| # | File | Answers | Skipping it causes |
|---|---|---|---|
| 1 | `CONTEXT.md` | Where the project is, what is frozen, what is undecided | Building against a stale or unfrozen contract |
| 2 | `CONVENTIONS.md` | The five Laws; how to name, log, error, seed, test | Law violations that CI catches late, or worse, doesn't |
| 3 | `DECISIONS.md` | What was already decided and why | Re-litigating a settled decision, or silently contradicting it |
| 4 | `GLOSSARY.md` §2 | The six overloaded terms | The most common defect class in this project: `CAUSES` written where only ordering is known |
| 5 | `PROGRESS.md` | What exists, what was deliberately omitted | Treating an intentional omission as a bug, or an untested module as trustworthy |
| 6 | `docs/architecture.md` | Layer ranks, forbidden edges, storage boundary, Run model | Writing an import the build will reject, or a write to the wrong store |
| 7 | `docs/prd.md` — relevant sections only | Product intent | — |

Then apply the model routing table (`CONVENTIONS.md` §2): architecture, ADRs, ambiguity
resolution, and gate reviews are Opus-tier work. Implementation against a fixed contract
is Sonnet-tier.

---

## 2. Verify before writing code

Run this checklist. Any `FAIL` blocks writing code until it is resolved or explicitly
waived in writing by the project owner.

| # | Check | How | On FAIL |
|---|---|---|---|
| 1 | The five Laws are present and identical in both files | `diff` the law blocks in `CONTEXT.md` §2 and `CONVENTIONS.md` §1 | File a defect. Do not pick a favorite; ask which is correct. |
| 2 | Your target module's status in `CONTEXT.md` §3 matches `PROGRESS.md` | Read both | File a defect (§3, class A or B). |
| 3 | Your target module's status matches the filesystem | Does the code exist? Does it match the claimed status? | File a defect (§3, class B). |
| 4 | The interfaces you will consume are `frozen`, or you accept they may change | `CONTEXT.md` §6 | If `draft`, your work is provisional. Say so in `PROGRESS.md`. |
| 5 | No interface you will *change* is `frozen` | `CONTEXT.md` §6 | Write an ADR first (`CONVENTIONS.md` §13). |
| 6 | Data contracts you depend on are not `unset` | `CONTEXT.md` §7 | You may not freeze anything. Proceed as `draft` only. |
| 7 | No Open Question that gates your module is unresolved | `CONTEXT.md` §8 "Unblocked by" | Use the proposed default **and record that you did** in `PROGRESS.md`. Never silently pick differently. |
| 8 | No `accepted` ADR contradicts your task | `DECISIONS.md` | Stop. Write the superseding ADR before any code. |
| 9 | Every term in your task is in `GLOSSARY.md` | Search | Add it, or ask. Do not coin a synonym for an existing term. |
| 10 | Your task is not on the deferred list | `CONTEXT.md` §10 | Stop. Reopening requires an ADR. |
| 11 | `make lint typecheck test` is green **before** you start | Run it | You are inheriting a broken tree. Report it; do not absorb it into your diff. |
| 12 | Your imports satisfy the layer ranks and forbidden edges | `python3 scripts/check_layers.py`; `docs/architecture.md` §1.4 | Restructure. A forbidden edge is a design error, not a lint to silence. |
| 13 | The determinism gate can run at all | `python3 scripts/check_determinism.py` | Exit 2 means NOT-YET-RUNNABLE (OQ-014), not pass. Record that you proceeded without it. |

---

## 3. Detecting that CONTEXT.md has gone stale

Staleness is mechanically detectable. Run these; do not rely on impression.

| # | Check | Command / method | Interpretation |
|---|---|---|---|
| S1 | Changelog gap | Newest `CONTEXT.md` §11 changelog date vs the newest source-file modification time (`find . -name '*.py' -o -name '*.ts' \| xargs ls -lt \| head`) | Code newer than the changelog ⇒ at least one commit skipped the same-commit doc rule. |
| S2 | Phantom completion | Any module `done` in `CONTEXT.md` §3 with no filled entry in `PROGRESS.md` | Status was advanced without a gate. Treat the module as `built-unverified`. |
| S3 | Unrecorded work | Any module directory containing code while `CONTEXT.md` §3 says `not-started` | Untracked work. Highest-risk staleness class — nobody knows what it assumes. |
| S4 | Frozen-contract drift | For each `frozen` row in `CONTEXT.md` §6, compare the signature in code to the contract document | A changed frozen interface without an ADR is a serious defect. |
| S5 | Version drift | Schema/ontology/dataset versions in code and output envelopes vs `CONTEXT.md` §7 | Divergence means outputs cannot be reproduced from the documented state. |
| S6 | Orphan vocabulary | Terms in code identifiers absent from `GLOSSARY.md`, and glossary terms absent from code | First direction: undocumented concept. Second: either not-yet-built (fine, if marked `[planned]`) or a removed concept still documented. |
| S7 | Zombie open questions | An OQ marked unresolved whose default is clearly implemented in code | The decision was made in code. Promote it to an ADR retroactively; do not just close the OQ. |
| S8 | Law erosion | `make laws` — runs the law-copy, LAW-DOMAIN (with self-test), layer-boundary, and dependency-policy checks | Any non-zero exit means a law is currently unenforced and must be reported as such, not worked around. |
| S9 | Risk staleness | Any `CONTEXT.md` §9 risk whose mitigation names a module that is still `not-started` | The mitigation is aspirational. It must read `NONE YET` instead. |

Run S1–S9 at the start of any session that follows a gap of more than one working session,
and always before a phase transition. Record the result in `CONTEXT.md` §11.

---

## 4. Reconciliation procedure — when docs and code disagree

### 4.0 The rule

**Code is the truth about what IS. Docs are the truth about what SHOULD BE.**

Two consequences, both non-negotiable:

- You may **never** silently edit a doc to match the code. That destroys the record of
  intent, which is the only thing that makes drift detectable. A silent doc edit is
  itself a defect.
- You may **never** assume the code is correct because it exists. Code that contradicts an
  `accepted` ADR is wrong code, not an implicit new decision.

### 4.1 Procedure

1. **Stop.** Do not continue the task that surfaced the discrepancy.
2. **Record both sides verbatim** — the doc statement with its file and section, the code
   behavior with its file and line, and how you observed it (test output, grep, read).
3. **Classify** using §4.2.
4. **File a defect** using the §4.3 template. Every discrepancy becomes a tracked defect,
   with no exception for "obviously just a typo" — typos in a contract are how two modules
   end up disagreeing.
5. **Route** per the class.
6. **Resolve**, then update `CONTEXT.md` §11 and, if a decision was made, `DECISIONS.md`.
7. **Only then** resume the original task.

### 4.2 Classification

| Class | Signature | Meaning | Route |
|---|---|---|---|
| **A — Doc lag** | Code is correct and intended; docs were simply not updated in the same commit | A process failure, not a design failure | Update the doc **and** note the missed same-commit update in `CONTEXT.md` §11. Identify the commit that skipped it. |
| **B — Code drift** | Code contradicts a doc that still expresses the intended design | The code is wrong | Fix the code. Do not touch the doc. Add a regression test that fails before the fix. |
| **C — Genuine conflict** | The doc expresses an intent that is wrong, infeasible, or superseded by what was learned while building | A real decision is required | **Write an ADR.** Never resolve C by editing prose. The ADR supersedes the prior decision and the doc is updated as a consequence of the ADR, citing it. |
| **D — Law violation** | Code violates one of the Five Inviolable Laws | `CRITICAL` | Stop all work. The code is wrong by definition; a law is never resolved in the code's favor. Fix, add a law test, and record in `CONTEXT.md` §11. |
| **E — Ambiguity** | Doc and code are both defensible because the doc is ambiguous | Not yet a conflict | Open an Open Question in `CONTEXT.md` §8 with a proposed default and cost-if-wrong. Promote to an ADR before the dependent interface is frozen. |

**Tie-breaks when classification is unclear:**
- If a Law is involved at all, it is **D**. No further analysis.
- If an `accepted` ADR is involved, it is **B** or **C** — never A. An ADR is intent, and
  intent does not "lag".
- If you cannot distinguish A from C, it is **C**. Writing an unnecessary ADR costs a page;
  a silent doc edit costs the project its audit trail.

### 4.3 Defect template

```markdown
### DEF-NNNN — <one line>
- Found: YYYY-MM-DD by <session/model>
- Class: A | B | C | D | E
- Doc says:  <file §section> — "<verbatim>"
- Code does: <file:line> — <observed behavior>
- Observed via: <command / test / grep — reproducible>
- Affects: <modules, interfaces from CONTEXT.md §6>
- Resolution: <fix code | update doc + note process failure | ADR-NNNN | OQ-NNN>
- Status: open | resolved YYYY-MM-DD
```

### 4.4 What is never an acceptable resolution

- Editing a doc to match code without classifying the discrepancy first.
- "The code has been like this for a while, so it must be intended."
- Resolving a Law violation by relaxing the Law.
- Closing an Open Question because code already picked a side, without writing the ADR.
- Marking a module `done` to make a status mismatch go away.

---

## 5. Handing off

Before ending a session that did meaningful work, leave the project in a state where the
next session needs nothing from you:

1. `CONTEXT.md` §3 status, §6 stability, §7 versions, §8 open questions, and §11 changelog
   are current.
2. `PROGRESS.md` for every module you touched has its **Deliberately NOT built** section
   filled — this is the field the next session will most regret being empty.
3. Every decision you made is an ADR, or an Open Question with a proposed default. Nothing
   important lives only in the conversation transcript.
4. Every default you *used* because an OQ was unresolved is recorded as used, in
   `PROGRESS.md`, naming the OQ.
5. `make lint typecheck test` is green, or the failure is documented with the reason.
6. Run the §3 staleness checks and record the result.

**A handoff that requires reading the previous session's transcript has failed.**

---

## 6. Defect log

Filed per §4.3. Every discrepancy becomes a tracked defect — there is no exception for
"obviously just a typo", because typos in a contract are how two modules end up disagreeing.

### DEF-0001 — LAW-DOMAIN lint matched whole words and caught almost no domain vocabulary
- Found: 2026-08-23 by review (Opus session)
- Class: **C — genuine conflict.** The code did exactly what `CONVENTIONS.md` §6 and
  ADR-0010 specified. The specification itself was wrong, so per §4.4 this could not be
  resolved by editing prose.
- Doc says: `CONVENTIONS.md` §6 — "**Matching:** case-insensitive, **word-boundary**
  (`\b`) — not naive substring."
- Code does: `scripts/check_domain_independence.py:57` (pre-fix) —
  `re.compile(r"\b(" + "|".join(BANNED_TOKENS) + r")\b", re.IGNORECASE)`. `\b` requires a
  non-word character after the token and `_` is a word character, so `warehouse_id`,
  `order_id`, `customer_name`, `WAREHOUSE_TABLE`, `orders`, `shipments`, `customers`, and
  `OrderId` all passed clean. Only the bare English word matched.
- Aggravating: the code comment attributed the exclusion of `reorder_key` to the underscore
  when it is caused by the `re` prefix — the rationale named the wrong mechanism. And
  `NEAR_MISSES` listed `shipments` and `customers_table_in_a_name` as words that must never
  fire, so the `--self-test` that ADR-0010 created to prevent this asserted the hole was
  correct behaviour.
- Observed via: appending four probes to `backend/src/causalog/core/temporal.py` —
  `warehouses plural`, `def resolve_shipments(orders)`, `WAREHOUSE_TABLE = "customers"`,
  `warehouse_id field` — and running `python3 scripts/check_domain_independence.py`:
  `LAW-DOMAIN: clean across 49 file(s). EXIT=0`. Post-fix the same probes yield
  6 violations and exit 1.
- Affects: LAW-DOMAIN across every reasoning package; `CONTEXT.md` R-10, which asserted
  "in force as of 2026-08-23" for the entire period the lint was ineffective.
- Resolution: **ADR-0019** (supersedes ADR-0010's matcher specification). Stem-prefix
  matching with a letter-only lookbehind and no suffix exceptions; self-test rebuilt as
  `MUST_FIRE`/`MUST_NOT_FIRE` with a guard that refuses a claimed false positive containing
  a banned stem; the four probes kept as regression cases; `--self-test` added to all four
  law scripts with negative pytest cases for the two that lacked them.
- Status: resolved 2026-08-23

**What this defect teaches, beyond its own fix:** a check's self-test is not evidence unless
something independent validates the test's own claims. `MUST_NOT_FIRE` is now validated by a
strict stem search that no matcher change can weaken. Before adding an entry to any
"expected clean" list in this repository, ask what would catch you if the entry were wrong.
