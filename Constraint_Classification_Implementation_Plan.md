# Relationship Constraint Classification — Implementation Plan
## (Hard vs. Soft FS Logic for Fast-Track Recovery Simulation)

Scope note: this plan covers only the constraint-classification feature — deciding which
FS relationships are legitimate fast-track (FS→SS) candidates and which are physically/
regulatorily locked. It deliberately excludes the ML trend-forecasting layer discussed
elsewhere; everything here is deterministic heuristics + rules + human review.

---

## 1. Objective

Give the what-if/recovery simulation engine a safe way to know **which FS relationships
it is allowed to propose converting to SS (or shortening the lag on)**, without needing
a PM to manually review every relationship in a schedule. The system should:

1. Auto-classify the relationships it can classify with high confidence.
2. Explicitly flag everything else as `unclassified` and keep it out of fast-track suggestions.
3. Let a PM classify the ambiguous remainder once, cheaply, in context.
4. Remember that classification permanently and reuse it — including across projects,
   where the same activity-pair pattern recurs.
5. Never let the simulation engine treat an `unclassified` or `hard_*` relationship as
   fast-trackable, even under time pressure.

---

## 2. Data Model

### 2.1 New field on the relationship/edge record

```
relationship_classification (per relationship, per project — not global):
  relationship_id            FK -> Relationship
  constraint_type            enum: HARD_PHYSICAL | HARD_REGULATORY | HARD_SAFETY
                                  | SOFT_RESOURCE | SOFT_COORDINATION | UNCLASSIFIED
  confidence                 float 0.0–1.0
  classification_source      enum: HEURISTIC_KEYWORD | HEURISTIC_LAG | HEURISTIC_CSI_JUMP
                                  | LIBRARY_MATCH | PM_REVIEWED
  rationale                  text   -- human-readable reason (which rule fired, or PM's note)
  reviewed_by                nullable user id
  reviewed_at                nullable timestamp
  library_pattern_id         nullable FK -> ClassificationPattern (see 2.2)
```

### 2.2 Reusable pattern library (the thing that makes this pay off over time)

```
ClassificationPattern:
  pattern_id
  match_type            enum: NAME_PAIR_REGEX | NAME_PAIR_FUZZY | CSI_PAIR
  predecessor_pattern    text   -- e.g. regex "concrete.*pour" or CSI division "03"
  successor_pattern      text   -- e.g. regex "formwork.*strike" or CSI division "03"
  constraint_type        enum (same as above, restricted to non-UNCLASSIFIED)
  min_lag_hrs             nullable float   -- optional supporting signal
  source                  enum: SEEDED | PM_CONFIRMED
  times_matched           int
  times_overridden        int   -- PM disagreed with a prior auto-classification from this pattern
  org_scope               enum: PROJECT | ORG   -- PM can promote a pattern from project-only to org-wide
```

`times_overridden` matters: if a seeded or auto-derived pattern keeps getting overridden
by PMs, that's a signal the heuristic is wrong and should be down-weighted or retired —
this is the feedback loop, without needing ML.

---

## 3. Classification Pipeline

Runs once per ingestion, on every relationship of type FS that doesn't already have a
`PM_REVIEWED` classification carried over from a prior snapshot (classifications persist
across snapshots for the same relationship — no need to re-classify unchanged logic).

```
for each FS relationship in the current snapshot:
    if already PM_REVIEWED (from a prior snapshot of this project) -> carry forward, skip
    if already matched by an org/project ClassificationPattern with high confidence -> apply, skip
    run heuristic stack (Section 4) in priority order
    if any heuristic fires with confidence >= AUTO_CLASSIFY_THRESHOLD -> apply, record source+rationale
    else -> UNCLASSIFIED, queued for PM review
```

### 3.1 Priority order of heuristics (highest-precedence first)

1. **Library pattern match** — exact or fuzzy match against `ClassificationPattern` (org-scope first, then project-scope). This is the cheapest, most reliable signal once the library has any history.
2. **Regulatory/safety keyword match** — highest-precedence heuristic *not* from the library, because false negatives here are the dangerous failure mode (suggesting fast-track on something that's actually a permit gate).
3. **Physical/curing keyword match**.
4. **Lag-duration correlation** — lag magnitude close to a known curing/inspection duration band.
5. **CSI division jump** — large division jump + FS relationship.
6. **Same-trade / same-crew heuristic** — pushes toward `SOFT_RESOURCE`, but only ever as a *supporting* signal combined with absence of any hard-keyword hit above, never standalone at high confidence (same-trade doesn't guarantee resource-only dependency).

Everything that doesn't clear `AUTO_CLASSIFY_THRESHOLD` through this stack stays
`UNCLASSIFIED` — no forced classification, no averaging multiple weak signals into a
confident one.

---

## 4. Heuristic Definitions (deterministic, no ML)

### 4.1 Regulatory/safety keyword match → HARD_REGULATORY / HARD_SAFETY

Maintain a small, editable keyword list (not hardcoded in application logic — stored as
config so a PM/scheduler can extend it without a deploy):

```
HARD_REGULATORY_TERMS = [
    "permit", "inspection", "inspect", "approval", "sign-off", "sign off",
    "AHJ", "code compliance", "hydro test", "hydrotest", "pressure test",
    "commissioning sign-off", "energiz", "utility release"
]
HARD_SAFETY_TERMS = [
    "loto", "lock-out", "lockout", "tag-out", "confined space",
    "scaffold cert", "fall protection", "excavation permit", "shoring"
]
```

Rule: if either the predecessor or successor activity name/description contains a term
from either list (case-insensitive, word-boundary match to avoid partial-word false
positives), classify `HARD_REGULATORY` or `HARD_SAFETY` respectively, confidence = 0.9.

### 4.2 Physical/curing keyword match → HARD_PHYSICAL

```
HARD_PHYSICAL_TERMS = [
    "cure", "cured", "curing", "dry", "dried", "drying", "set", "setting",
    "weld", "welding", "ndt", "backfill", "compaction", "settle", "settlement",
    "fireproofing cure", "strip form", "strike form", "de-shore", "deshore"
]
```

Same match logic, confidence = 0.85. Slightly lower than regulatory because curing-adjacent
words occasionally appear in soft-dependency activity names too (e.g., a submittal called
"Cure Schedule Review") — keep confidence just under the regulatory tier so ties resolve
toward the safer bucket if both somehow fire (regulatory wins).

### 4.3 Lag-duration correlation → HARD_PHYSICAL (supporting signal)

If the relationship has a positive lag and that lag falls within a configurable band
around known curing/inspection durations for the matched activity type (e.g., 48–96 hrs
for concrete cure, 24–48 hrs for coating dry time — these bands come from a small
reference table, not invented per-project), add 0.15 to whatever confidence the keyword
match produced, capped at 0.95. On its own (no keyword hit), a lag match alone tops out
at confidence 0.6 — not enough to auto-classify by default, but enough to prioritize in
the PM review queue.

### 4.4 CSI division jump → weak HARD_PHYSICAL signal

If predecessor and successor activity codes map to CSI MasterFormat divisions and the
jump is large (e.g., Division 03 Concrete → Division 09 Finishes, skipping 04-08), add a
small confidence bump (0.1) toward `HARD_PHYSICAL` — division jumps that large are rarely
resource-scheduling artifacts. This never fires alone at auto-classify confidence; it's a
tiebreaker/prioritization signal only.

### 4.5 Same-trade / same-crew → SOFT_RESOURCE (supporting signal, never standalone)

If predecessor and successor share the same trade/discipline activity code, **and none of
4.1–4.4 fired**, this nudges toward `SOFT_RESOURCE` at confidence 0.55 — below
`AUTO_CLASSIFY_THRESHOLD`, so it lands in the review queue pre-tagged with a suggested
classification for the PM to confirm quickly rather than classify from scratch.

### 4.6 Threshold

```
AUTO_CLASSIFY_THRESHOLD = 0.80   -- tune after pilot review (Section 8)
```

Anything at or above this auto-classifies. Anything below queues for PM review, pre-sorted
by descending confidence so the PM burns through the "almost certain" ones fastest.

---

## 5. PM Review Queue

### 5.1 What the PM sees per item

- Predecessor and successor activity name, code, WBS path, trade/discipline
- Relationship type, lag, and (if available) the heuristic's best guess + which rule
  produced it + confidence
- One-click classification buttons: Hard – Physical / Hard – Regulatory / Hard – Safety /
  Soft – Resource / Soft – Coordination
- Optional free-text rationale field (feeds `rationale` and helps future pattern-matching
  by keyword expansion)
- "Apply to similar relationships" checkbox — if checked, the classification is promoted
  into a new `ClassificationPattern` (project-scoped by default; PM can promote to
  org-scoped separately, deliberately, so one PM's one-off judgment doesn't silently
  become an org-wide rule)

### 5.2 Queue ordering

1. Relationships already on the project's Longest Path / near-critical (these matter most
   for the what-if engine — review these first even if confidence is lower priority
   otherwise)
2. Then descending by pre-tagged confidence from Section 4.5's weak signal
3. Then everything else

### 5.3 Batch operations

PMs should be able to select multiple queue items with identical or near-identical
activity-name patterns and classify them in one action — this is what actually makes
reviewing a 1,000-relationship schedule tractable (a repetitive "Level N Pour → Level N
Formwork Strike" pattern across 40 floors should be a five-second batch action, not 40
individual clicks).

---

## 6. Integration with the Simulation Engine

The recovery/what-if engine (fast-track lever) queries `relationship_classification`
before ever proposing an FS→SS conversion:

```
def is_fasttrack_candidate(relationship) -> bool:
    cls = get_classification(relationship)
    if cls is None or cls.constraint_type == UNCLASSIFIED:
        return False
    return cls.constraint_type in (SOFT_RESOURCE, SOFT_COORDINATION)
```

- `HARD_*` and `UNCLASSIFIED` relationships are never offered as fast-track candidates,
  full stop — no override flag, no "force" mode, even for an admin. If a PM genuinely
  believes a `HARD_*` relationship is fast-trackable, the correct action is to
  **re-classify it** (with rationale recorded), not to bypass the check for one simulation
  run. This keeps the audit trail honest.
- Every simulation result that used a `SOFT_*` relationship in its lever set should cite
  which relationships were converted and their classification source
  (`classification_source` + `reviewed_by` if PM-reviewed), so the recovery report is
  traceable back to a human decision or a specific rule, not a black box.

---

## 7. Persistence Across Snapshots

Classifications are keyed to a stable relationship identity (predecessor task code +
successor task code + relationship type — not the raw XER relationship ID, which can
change between snapshots even for logically-the-same link, depending on how the fuzzy
activity matcher resolves renames). When a new snapshot is ingested:

1. For each FS relationship in the new snapshot, look up whether the same
   predecessor-code/successor-code/type triple was previously classified.
2. If yes, carry the classification forward unchanged (no re-review needed) — but flag it
   for re-review if the lag changed materially (>25%) or if the predecessor/successor
   activity names changed enough that the fuzzy matcher's confidence for "same
   relationship" itself is below its own threshold. Don't silently carry forward a
   classification onto a relationship the system isn't actually confident is the same
   link.

---

## 8. Rollout Plan

**Phase 1 — Heuristic engine + data model (1–2 weeks)**
Build the classification table, pattern library table, and the deterministic heuristic
stack from Section 4. Run it read-only against a handful of real historical schedules and
manually audit a sample of ~100 classifications per confidence band (0.8–0.85, 0.85–0.9,
0.9+) to sanity-check the keyword lists and thresholds before anything touches the
simulation engine.

**Phase 2 — Review queue UI (1–2 weeks)**
Build the queue, single-item and batch classification actions, and the
"promote-to-pattern" flow. Pilot with one real project and one PM; track how many items
land in queue vs. auto-classified, and how often the PM's judgment disagrees with a
pre-tagged suggestion (this disagreement rate is your real threshold-tuning signal, not a
guess).

**Phase 3 — Simulation engine gating (1 week)**
Wire `is_fasttrack_candidate` into the what-if engine's lever generator. Add the
classification-source citation to simulation output. Regression-test that no `HARD_*` or
`UNCLASSIFIED` relationship can ever appear as a fast-track lever, including via
combinatorial/optimization search paths (Section 3.3 of the earlier optimization design)
— this needs an explicit test, not just code review, since a search algorithm exploring a
large lever space is exactly the kind of place a missed guard clause would slip through
silently.

**Phase 4 — Pattern library maturation (ongoing)**
Track `times_matched` / `times_overridden` per pattern. Any pattern with an override rate
above a set threshold (start at 20%, tune from data) gets flagged for review — either the
pattern is too broad (needs a narrower regex/CSI scope) or it was wrong from the start.
This is the whole feedback loop the plan needs — no model training required, just
counting agreements vs. disagreements per rule.

---

## 9. What Explicitly Stays Out of Scope Here

- No ML model predicting classification from historical data — everything above is rule-
  based and human-confirmed by design, per your instruction.
- No automatic promotion of project-scoped patterns to org-scoped patterns — that's
  always a deliberate PM action, never inferred from match volume alone.
- No bypass/override path in the simulation engine for `HARD_*` relationships — if that's
  ever needed, it should be its own deliberately-designed, separately-audited feature, not
  a flag on this one.
