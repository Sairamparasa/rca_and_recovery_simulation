# AI-Assisted Schedule Driver Detection & Recovery Simulation System (`arth_rca`)

An enterprise-grade, deterministic schedule intelligence and recovery simulation engine for Primavera P6 schedules.

## 📁 Architecture & Specifications

The authoritative architecture, data model, constraint classification rules, and implementation blueprints are located in [`docs/architecture/`](file:///c:/Users/saira/OneDrive/Desktop/arth_rca/docs/architecture):

- 📘 [**Authoritative Architecture Reference Guide**](file:///c:/Users/saira/OneDrive/Desktop/arth_rca/docs/architecture/ARCHITECTURE_REFERENCE.md)
- 📘 [**Complete Implementation Plan**](file:///c:/Users/saira/OneDrive/Desktop/arth_rca/docs/architecture/Complete_Implementation_Plan.md)
- 📘 [**Constraint Classification Implementation Plan**](file:///c:/Users/saira/OneDrive/Desktop/arth_rca/docs/architecture/Constraint_Classification_Implementation_Plan.md)

> **Key Note:** All architectural, structural, and schema decisions must strictly adhere to these authoritative documents.

---

## 🏛 System Layers

1. **Presentation Layer:** Interactive Driver Dashboards, What-If Workspaces, Graph Visualizations (Cytoscape.js), PM Review Queue, Historical Trend Views.
2. **AI Reasoning Layer (LLM):** Grounded narrative generation, NL-to-query translation, recommendation framing with strict Certainty-Tier tracking (`FACT`, `INFERENCE`, `MODELED`, `SIMULATION_DEPENDENT`).
3. **Analytics & Optimization Layer:** Driver detection & root-cause classifier, impact ranking, DCMA 14-point health check, What-If simulation engine, and Pareto-frontier combinatorial optimizer (ILP + Metaheuristics).
4. **Deterministic CPM Core:** Pure-function forward/backward pass, calendar-aware date math, float calculations, driving-relationship detection, longest path computation, and out-of-sequence resolution.
5. **Data & Storage Layer:** Immutable snapshot schema, XER parser, PostgreSQL database, stable relationship identity hashing, and NetworkX graph projections.
