# Complete Implementation Plan
## AI-Assisted Schedule Driver Detection & Recovery Simulation System

**Scope note:** Per current direction, this plan excludes the ML trend-forecasting/
prediction module discussed earlier. Trend data is still captured and displayed
(erosion charts, driver churn, DCMA score history) — but purely as historical
reporting, with no predictive model attached. Everything else from the original
architecture is included at full implementation depth: deterministic CPM engine,
driver detection, constraint classification, what-if simulation, combinatorial
optimization, and the LLM reasoning layer.

---

## 1. System Overview

```
┌───────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER — Dashboard | NL Query | Reports | API      │
├───────────────────────────────────────────────────────────────┤
│  AI REASONING LAYER — LLM narrative, NL→query, recommendation   │
│  framing (grounded against structured data, never invents nums) │
├───────────────────────────────────────────────────────────────┤
│  ANALYTICS LAYER — Driver detection, impact ranking, DCMA        │
│  checks, constraint classification, what-if engine, optimizer   │
├───────────────────────────────────────────────────────────────┤
│  CPM CORE — Calendar-aware forward/backward pass, float,        │
│  driving-relationship detection, longest path (deterministic)   │
├───────────────────────────────────────────────────────────────┤
│  DATA LAYER — XER parser, relational DB, graph DB, snapshot      │
│  history store, object storage for raw files                    │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. Data Model

### 2.1 Core relational schema (Postgres)

```
Organization
  id, name, created_at

Project
  id, org_id, name, p6_project_id, calendar_default_id, created_at

Snapshot
  id, project_id, imported_at, source_filename, data_date,
  is_baseline (bool), baseline_revision_reason (nullable),
  raw_file_ref (object storage key)

Activity   (one row per activity per snapshot — snapshots are immutable)
  id, snapshot_id, task_code, name, wbs_path, calendar_id,
  original_duration, remaining_duration, percent_complete, status,
  early_start, early_finish, late_start, late_finish,
  total_float, free_float, constraint_type, constraint_date,
  is_milestone (bool)

Relationship  (edges, one row per relationship per snapshot)
  id, snapshot_id, predecessor_activity_id, successor_activity_id,
  relationship_type (FS/SS/FF/SF), lag, is_driving (computed bool)

Calendar
  id, project_id, name, working_days_json, exceptions_json

Resource / ActivityResource   (optional, only if cost/resource loaded)
  standard resource assignment fields — budgeted units, cost, actual units

DriverRecord   (computed, one row per driver per snapshot)
  id, snapshot_id, head_activity_id, root_cause_type
    (constraint | logic_change | out_of_sequence | external_delay | unresolved),
  float_days, downstream_activity_count, impact_score,
  milestones_blocked (array of activity_ids)

DrivingChain   (edges within a driver's tree — supports both directions)
  id, driver_record_id, activity_id, parent_activity_id (nullable for head),
  direction (backward_root_trace | forward_blast_radius),
  relationship_type, lag, is_convergence_node (bool)

RelationshipClassification   (see Section 5 — constraint classification feature)
  relationship_key (stable predecessor_code+successor_code+type — see 2.2),
  project_id, constraint_type, confidence, classification_source,
  rationale, reviewed_by, reviewed_at, library_pattern_id

ClassificationPattern
  id, org_id (nullable), project_id (nullable), match_type,
  predecessor_pattern, successor_pattern, constraint_type,
  min_lag_hrs, source, times_matched, times_overridden

Scenario   (what-if simulation runs)
  id, project_id, baseline_snapshot_id, created_by, created_at,
  levers_applied_json, status (proposed | approved | tracked | rejected),
  result_finish_date, result_float_summary_json, result_cost_delta,
  engine_version

DCMAHealthCheck   (one row per snapshot)
  id, snapshot_id, missing_logic_pct, negative_float_pct,
  high_float_outlier_pct, hard_constraint_count, negative_lag_count,
  critical_path_length_index, invalid_date_count, computed_at

EvidenceLedgerEntry   (audit trail linking a diagnosis/driver claim to source facts)
  id, driver_record_id or scenario_id, claim_text, certainty_tier
    (FACT | INFERENCE | MODELED | SIMULATION_DEPENDENT), source_ref
```

### 2.2 Stable relationship identity (needed for classification persistence and change tracking)

Since raw XER relationship IDs can shift between snapshots even for a logically unchanged
link, define a stable key:

```
relationship_key = hash(predecessor_task_code, successor_task_code, relationship_type)
```

Used to carry `RelationshipClassification` and driving-chain comparisons forward across
snapshots without re-deriving them from scratch each time.

### 2.3 Graph representation

Mirror `Activity`/`Relationship` for the **current snapshot only** into a graph store
(Neo4j, or an in-memory graph built per request if snapshot size doesn't justify a
standing graph DB — see Section 8 for the build-vs-defer decision). The relational tables
remain the system of record across all snapshots; the graph is a derived, rebuildable
view used for traversal-heavy operations (Trace Logic, Longest Path, downstream tree
construction).

---

## 3. CPM Core Engine

### 3.1 Responsibilities

- Parse calendars (working days, exceptions, per-activity calendar assignment).
- Forward pass: Early Start/Early Finish per activity, respecting relationship type, lag,
  and calendar.
- Backward pass: Late Start/Late Finish from project finish (or a Must-Finish-By
  constraint if present).
- Total Float = LS − ES (confirm this matches the source schedule's configured float
  mode — P6 supports more than one convention; detect and match it, don't assume).
- Free Float per activity.
- Driving-relationship flag per edge: an FS predecessor is driving its successor if
  `successor.ES == predecessor.EF + lag` (analogous checks for SS/FF/SF).
- Constraint handling: Mandatory Start/Finish, As-Late-As-Possible, Start/Finish-On-or-
  Before/After — resolved exactly per source scheduling tool's rules.
- Out-of-sequence handling: support both "retained logic" and "progress override" modes,
  configurable per project (must match how the source schedule is actually configured,
  not a fixed assumption).

### 3.2 Implementation approach

- Build in Python first (`networkx` for graph structure is a reasonable starting point,
  though the CPM math itself — the forward/backward pass — should be hand-implemented
  rather than relying on a generic shortest/longest-path library, since calendar-aware
  duration arithmetic doesn't map cleanly onto standard graph algorithms).
- Structure the engine as a pure function: `(activities, relationships, calendars,
  project_constraints) -> (dates, float, driving_flags)` — no side effects, no DB access
  inside the engine itself. This makes it trivially reusable by both the diagnostic
  pipeline and the what-if simulator (Section 6), and trivially testable in isolation.
- Performance: for schedules in the 10–20k activity range, a well-written Python
  implementation should complete a full forward+backward pass in low single-digit
  seconds. If profiling later shows this is a bottleneck at higher scale, the pure-function
  boundary above makes it straightforward to reimplement the hot path in a compiled
  language without touching anything upstream or downstream.

### 3.3 Validation (mandatory gate before anything else is trusted)

- Assemble a regression suite of real schedules (anonymized) covering: multiple
  calendars, mixed relationship types, negative lag, various constraint types, both OOS
  modes.
- For each, compare every activity's ES/EF/LS/LF/TF against the source tool's native
  output. Target: exact match to the day on 100% of the suite before Phase 2 begins.
- Re-run this suite on every change to the CPM engine, permanently, as a CI gate.

---

## 4. Driver Detection & Impact Ranking

### 4.1 Driver identification

1. Run CPM engine on current snapshot.
2. Collect all activities with negative (or, if desired, below-threshold) total float.
3. For each, traverse driving relationships backward until reaching an activity whose own
   negative float is *not* explained by an upstream negative-float activity in the same
   set — that activity is a driver head.
4. From each driver head, traverse driving relationships forward to build the full
   downstream tree (the "blast radius").
5. Mark any activity appearing in more than one driver's downstream tree as a
   convergence node.

### 4.2 Root-cause typing (deterministic classification of *why* a driver is late)

Classify each driver head using available signals:
- `constraint`: driven by a hard constraint date rather than logic.
- `out_of_sequence`: flagged OOS in the source data.
- `logic_change`: a relationship was added/removed/modified since the prior snapshot in a
  way that directly explains the new negative float (requires snapshot-to-snapshot diff —
  see Section 7).
- `external_delay`: negative float traces back to an activity with no predecessors in this
  schedule (a true external input, e.g., an owner-furnished item or permit).
- `unresolved`: none of the above apply cleanly — flag for manual review rather than
  guessing.

### 4.3 Impact scoring

```
impact_score = downstream_activity_count
             × float_magnitude_weight(driver.float_days)
             × milestone_weight(count of contractual/key milestones in downstream tree)
```

Weights should be configurable (project-specific — a milestone-heavy commercial fit-out
and a linear infrastructure project will reasonably want different weightings), stored
per-project rather than hardcoded.

### 4.4 Output structure

Ranked driver list with drill-down to: root-cause type, backward trace, forward tree,
convergence-node flags, and a project-level rollup ("N drivers account for X% of
negative-float activities").

---

## 5. Constraint Classification (Hard vs. Soft FS)

Full detail already specified in the prior plan (heuristic stack: regulatory/safety
keyword match, physical/curing keyword match, lag-duration correlation, CSI division
jump, same-trade supporting signal; `AUTO_CLASSIFY_THRESHOLD = 0.80`; PM review queue for
everything below threshold; reusable pattern library with `times_matched` /
`times_overridden` tracking). Summary of what integrates into this build:

- `RelationshipClassification` and `ClassificationPattern` tables (Section 2.1).
- Classification pipeline runs once per ingestion, after CPM engine and driver detection,
  scoped to FS relationships appearing in any driver's downstream tree (no need to
  classify relationships nowhere near a negative-float chain — prioritize compute where
  it matters).
- PM review queue UI, ordered by Longest-Path proximity first, then confidence.
- Gate function (`is_fasttrack_candidate`) consumed directly by the what-if engine's lever
  generator (Section 6) — hard requirement, no bypass path.

---

## 6. What-If / Recovery Simulation Engine

### 6.1 Recovery levers (programmatic operations on a cloned graph)

| Lever | Operation | Guard |
|---|---|---|
| Crash | reduce duration by N days | requires cost/resource curve if cost delta is to be reported |
| Fast-track | FS → SS conversion, or lag reduction | must pass `is_fasttrack_candidate` (Section 5) |
| Logic change | remove/modify a relationship | flagged for PM approval before "applying" even in simulation |
| Constraint relaxation | remove/modify a hard constraint date | flagged for PM approval — constraints often exist for contractual reasons |
| Resequencing | reorder non-dependent activities | only between activities with no existing logic tie |
| Calendar change | assign higher-capacity calendar (weekend work, extended shift) | should carry a cost/resource-strain note even without full cost integration |
| Activity split | divide one activity into parallel sub-activities of equal total work | requires the activity to be resource-loaded to validate feasibility |

### 6.2 Simulation mechanics

```
def run_scenario(baseline_snapshot, levers):
    graph = clone_graph(baseline_snapshot)
    for lever in levers:
        validate_lever(lever, graph)      # includes is_fasttrack_candidate gate
        apply_lever(graph, lever)
    result = run_cpm_engine(graph)        # same engine as Section 3, pure function
    return diff_against_baseline(baseline_snapshot, result)
```

- `diff_against_baseline` reports: new project finish date, float delta per activity
  (project-wide and specifically along the affected chain), whether the critical/driving
  path shifted elsewhere, and cost delta where applicable.
- **Scoped recomputation for performance**: for a single-lever scenario touching one
  driver's chain, it is not necessary to re-run CPM on the entire schedule — only the
  forward pass from the affected activity onward needs recomputing, provided nothing
  upstream changed. Design the engine's pure-function interface (Section 3.2) to accept a
  subgraph and a set of "fixed" boundary dates so this optimization is available without
  restructuring the core engine later. Always run a full-schedule pass before presenting a
  scenario as final, to catch the case where a parallel path elsewhere becomes newly
  controlling — the scoped pass is a fast preview, not the authoritative result.

### 6.3 Phased lever testing

- **Phase A — single lever per top-N drivers**: exhaustive, fast, gives a clear per-driver
  "what works" picture.
- **Phase B — combinatorial**: see Section 7 (optimization).

---

## 7. Combinatorial Optimization

### 7.1 Problem framing

Classic Time-Cost Trade-off Problem: minimize project finish date (or total negative
float) subject to a budget constraint and to the classification/approval guards from
Sections 5–6.

### 7.2 Method selection by scale

- **Bounded/small** (a handful of top drivers, limited lever combinations): Integer Linear
  Programming via OR-Tools or PuLP — exact solution, fast enough to run interactively.
- **Larger combinatorial space** (many drivers, many lever types, cross-driver
  interactions via convergence nodes): metaheuristic search — simulated annealing or a
  genetic algorithm — to explore the space without brute-forcing every combination.
  Fitness function = weighted combination of days recovered and cost, matching the impact-
  score weighting philosophy from Section 4.3.

### 7.3 Output

A Pareto frontier of scenarios (days recovered vs. cost), not a single "best" answer —
the PM/client makes the actual trade-off decision; the system's job is to make that
trade-off space visible and computed correctly, not to pick for them.

---

## 8. Snapshot Comparison & Change Tracking (no forecasting, pure historical diff)

Since ML forecasting is explicitly out of scope here, this layer is limited to
**deterministic comparison and display**, not prediction:

- Snapshot-to-snapshot diff: relationship additions/deletions/modifications, duration
  changes, constraint changes, new/resolved/persistent drivers (driver churn).
- Float trend per activity/driver/milestone across all snapshots to date — stored and
  charted as historical fact, with no extrapolation applied.
- DCMA health score per snapshot, trended the same way.
- Baseline-vs-current cumulative slippage per milestone.

All of this feeds the LLM narrative layer (Section 9) as grounded historical fact — the
LLM may *describe* a trend it's given ("float has declined for three consecutive
snapshots"), but should not be prompted to project it forward into a predicted date,
since that would reintroduce a forecasting claim through the back door without the
rigor a real forecasting module would require.

---

## 9. AI Reasoning Layer (LLM)

### 9.1 Scope

- Narrative report generation from structured diagnostic/trend output (grounded — the
  LLM is given the actual computed numbers and asked to write about them, never asked to
  produce numbers itself).
- Natural-language query interface: parse the question into a structured query against
  driver/scenario/trend data, execute deterministically, hand the LLM the result set to
  phrase as an answer.
- Recommendation framing: given a completed simulation's Pareto frontier, help articulate
  qualitative trade-offs — always labeled as a suggestion, always traceable to which
  scenario/driver it refers to.
- Root-cause hypothesis text for `unresolved`-typed drivers (Section 4.2) — explicitly
  flagged as a hypothesis needing human confirmation, never presented as the same
  certainty tier as a `FACT`-derived diagnosis.

### 9.2 Guardrails (hard requirements, not aspirational)

- No autonomous edits to any schedule, baseline, or classification — every action needs
  explicit human approval, tracked with `reviewed_by`/`approved_by` fields.
- Every number in LLM output must be traceable to a specific `Scenario`, `DriverRecord`,
  or `DCMAHealthCheck` row — implement this as a templating/grounding step (structured
  data → prompt → text), not free generation from a general prompt.
- Certainty-tier labeling (`FACT` / `INFERENCE` / `MODELED` / `SIMULATION_DEPENDENT`)
  carried through from the analytics layer into every LLM-generated sentence that touches
  those claims.

---

## 10. API Layer

REST (FastAPI or equivalent) exposing:

```
POST   /projects/{id}/snapshots            — upload/ingest a new XER
GET    /snapshots/{id}/drivers             — ranked driver list
GET    /drivers/{id}/chain                 — backward + forward driving chain
GET    /snapshots/{id}/dcma                — health check results
GET    /relationships/classification-queue — PM review queue
POST   /relationships/{key}/classify       — submit a classification
POST   /scenarios                          — run a what-if scenario
GET    /scenarios/{id}                     — scenario result + diff
POST   /scenarios/optimize                 — combinatorial search request
GET    /snapshots/{id}/trend               — historical trend data (no prediction)
POST   /query                              — natural-language query endpoint
GET    /snapshots/{id}/report              — generated narrative report
```

All write endpoints (`classify`, scenario approval, report generation) require
authenticated user context — every classification and every approved scenario needs an
attributable human.

---

## 11. Frontend

- **Driver dashboard** (primary view): ranked list, drill-down to chain, project-level
  rollup summary.
- **What-if workspace**: lever selection, side-by-side scenario comparison table, Pareto
  frontier chart.
- **Classification review queue**: single-item and batch review UI (Section 5).
- **Trend view**: erosion charts, DCMA history, driver churn — historical only, per
  Section 8.
- **NL query box**.
- Graph-visualization component (e.g., Cytoscape.js) for driving-chain and downstream-tree
  display — this is worth investing real design effort in, since a badly rendered graph
  of 300+ nodes is worse than the ranked list it's meant to support.

---

## 12. Technology Stack

| Layer | Choice |
|---|---|
| XER parsing | Python — existing open-source parser as a base, extended/hardened as needed |
| CPM engine | Python, pure-function design (Section 3.2) |
| Relational DB | PostgreSQL |
| Graph store | Neo4j if standing graph queries justify it; otherwise in-process graph (networkx) rebuilt per request — decide based on actual traversal performance measured in Phase 1, not upfront assumption |
| Optimization | OR-Tools / PuLP (ILP); custom or DEAP (genetic algorithm / simulated annealing) |
| LLM | API-based (Claude), grounded/templated prompting, no fine-tuning needed initially |
| Backend API | FastAPI |
| Frontend | React, Recharts/D3 for charts, Cytoscape.js for graph views |
| Auth | Standard org/project RBAC |
| Deployment | Containerized; confirm data-residency requirements early (construction/EPC clients frequently require on-prem or single-tenant VPC) |

---

## 13. Phased Roadmap

**Phase 0 — Foundation (4–5 weeks)**
XER parser, core data model, ingestion pipeline, CPM engine + full validation suite
(Section 3.3). No downstream feature begins until this passes.

**Phase 1 — Driver Diagnostics (4–5 weeks)**
Driving-relationship detection, driver clustering, root-cause typing, impact ranking,
DCMA health checks. Dashboard v1 (ranked drivers + drill-down).

**Phase 2 — Constraint Classification (3 weeks)**
Heuristic stack, classification data model, PM review queue UI, pattern library with
override tracking.

**Phase 3 — What-If Engine (5–6 weeks)**
Lever library, single-lever simulation, scenario comparison UI, scoped-recomputation
performance path.

**Phase 4 — Optimization (4–5 weeks)**
ILP solver for bounded cases; metaheuristic search for larger combinatorial spaces;
Pareto frontier output and UI.

**Phase 5 — Trend & Historical Reporting (3 weeks)**
Snapshot diffing, driver churn tracking, DCMA/float trend charts — historical display
only, per the explicit exclusion of predictive modeling in this plan.

**Phase 6 — AI Reasoning Layer (4–5 weeks)**
Grounded narrative generation, NL query interface, recommendation framing, certainty-tier
propagation into generated text.

**Recommended pilot checkpoint:** after Phase 2, run the system against 2–3 real, messy
client schedules end-to-end (ingest → drivers → classification queue) before committing
to the full Phase 3+ build. This is the point where real-world data will surface wrong
assumptions in the CPM engine, the classification keyword lists, and the impact-ranking
weights — cheaper to find now than after the simulation and optimization layers are built
on top of a shaky foundation.

---

## 14. Testing & Validation Strategy

- CPM engine: permanent regression suite against source-tool output (Section 3.3),
  re-run on every change.
- Driver detection: unit tests with constructed schedules of known driver structure
  (single chain, branching, converging, multiple independent drivers) to verify tree
  construction and convergence-node flagging.
- Classification: audit sample of ~100 auto-classifications per confidence band before
  enabling auto-classify in a live project (Section 8 of the prior classification plan);
  ongoing override-rate monitoring per pattern.
- Simulation engine: regression test confirming no `HARD_*` or `UNCLASSIFIED`
  relationship can ever surface as a fast-track lever, including through the
  optimization/combinatorial search path specifically (a search algorithm exploring a
  large lever space is where a missed guard clause is most likely to slip through).
- LLM layer: every generated report/answer in test suite checked against source data for
  numeric accuracy (no invented figures) and correct certainty-tier labeling.

---

## 15. Team & Risk Summary

**Team:** scheduling/P6 domain expert (non-negotiable), 2+ backend engineers (Python,
graph/data modeling, CPM implementation), 1 frontend engineer (dashboard + graph
visualization), OR/optimization specialist (can be part-time), applied-AI engineer for
the grounded LLM layer.

**Key risks:**
- CPM engine mismatch with source tool output → mitigated by the mandatory validation
  gate before any feature is built on top.
- Classification heuristics wrong on unfamiliar project types (e.g., non-construction
  domains where the keyword lists don't apply) → mitigated by low
  `AUTO_CLASSIFY_THRESHOLD` defaults and the PM review queue as the safety net, plus
  per-project/org pattern scoping rather than one global list.
- Optimization search proposing infeasible combinations (e.g., two levers that
  individually pass validation but conflict when combined) → mitigate by re-validating the
  full lever set (not just each lever individually) before accepting any combinatorial
  scenario result.
- Scope creep toward autonomous schedule editing → held explicitly out of scope throughout
  this plan; every write action requires human approval.
