# APRD (AI Product Requirements Document)

# Project Name

**Project CausaLog**
*A Causal Intelligence Engine for Event-Driven Systems*

**Version:** 1.0

**Document Status:** Living Document

**Document Purpose**

This document serves as the canonical source of truth for the engineering, AI, product, and research teams. Every architectural decision, implementation detail, and future extension must remain consistent with the principles defined herein.

---

# 1. Executive Summary

Modern enterprise software excels at recording events but performs poorly at explaining them.

When an order is delayed, inventory becomes unavailable, or a shipment fails, existing systems typically provide:

* Status
* Timestamp
* Prediction
* Dashboard metrics

These systems rarely answer the questions decision-makers actually ask:

* Why did this happen?
* Where did it originate?
* Which events amplified the problem?
* Could this have been prevented?
* What is the smallest intervention that would have prevented the outcome?
* If one event had been different, would the outcome still occur?

This project aims to bridge that gap.

Instead of treating business operations as isolated records, the system models them as interconnected chains of causality.

The first implementation will use the **DataCo SMART Supply Chain for Big Data Analysis** dataset, but the architecture is intentionally domain-agnostic so that the same engine can later support manufacturing, healthcare, cybersecurity, software engineering, finance, and other event-driven systems.

---

# 2. Vision

Build an AI system that transforms historical event data into an explainable causal graph capable of:

* reconstructing causal chains,
* identifying probable root causes,
* quantifying propagation,
* detecting reinforcing feedback loops,
* simulating alternative scenarios,
* recommending optimal interventions.

The long-term objective is to move enterprise decision support from descriptive analytics toward causal intelligence.

---

# 3. Product Philosophy

The system is founded on one core principle:

> Every observable outcome is the consequence of one or more interacting events occurring over time.

An observed failure is therefore not the beginning of analysis.

It is the end of a causal sequence.

The software exists to reconstruct that sequence.

---

# 4. Problem Statement

Current logistics software generally answers:

"What is happening?"

Sometimes it answers:

"What is likely to happen?"

Very rarely does it answer:

"Why did this happen?"

Even more rarely:

"What could have prevented it?"

As a consequence:

* recurring operational failures remain unresolved,
* organizations repeatedly treat symptoms,
* intervention decisions depend heavily on human expertise,
* institutional knowledge is lost,
* postmortem analyses are slow and inconsistent.

---

# 5. Opportunity

Organizations increasingly collect massive operational datasets.

Examples include:

* ERP systems
* Warehouse Management Systems
* Transportation Management Systems
* CRM platforms
* IoT sensors
* GPS streams
* Manufacturing logs
* Audit trails

Most of these systems capture events but never transform them into explicit causal knowledge.

This project addresses that gap.

---

# 6. Product Scope

## Included

The first release focuses on:

* historical event reconstruction,
* temporal ordering,
* causal graph generation,
* root cause identification,
* propagation analysis,
* intervention recommendation,
* explainable visualization.

## Excluded (Version 1)

* real-time streaming inference,
* autonomous decision execution,
* reinforcement learning,
* multi-company optimization,
* digital twin simulation,
* predictive maintenance.

These capabilities are future extensions.

---

# 7. Initial Domain

Primary Dataset

DataCo SMART Supply Chain for Big Data Analysis

The dataset will function as the reference implementation.

The engine itself must never become dependent on logistics-specific concepts.

All logistics terminology must remain configurable through domain definitions rather than embedded into algorithms.

---

# 8. Long-Term Vision

The same reasoning engine should later operate on:

* hospitals,
* manufacturing,
* cybersecurity,
* banking,
* aviation,
* software engineering,
* public administration,
* smart cities.

Only the domain ontology changes.

The reasoning engine remains unchanged.

---

# 9. Guiding Principles

## Principle 1

Events are first-class entities.

Rows are not.

---

## Principle 2

Time matters.

Every causal explanation must respect temporal ordering.

An event cannot explain another event that occurred before it.

---

## Principle 3

Correlation is evidence.

Not proof.

The engine must distinguish statistical association from causal confidence.

---

## Principle 4

Every explanation must be inspectable.

Black-box reasoning is unacceptable.

The user must be able to inspect every inferred relationship.

---

## Principle 5

Every recommendation must identify:

* expected benefit,
* confidence,
* supporting evidence,
* assumptions.

---

# 10. Primary Users

## Operations Manager

Needs rapid explanation of operational failures.

---

## Supply Chain Analyst

Needs historical investigation.

---

## Executive Leadership

Needs strategic patterns rather than individual incidents.

---

## Data Scientist

Needs causal graphs and supporting evidence.

---

## Process Improvement Team

Needs intervention opportunities.

---

# 11. Core Product Capabilities

The platform must answer five categories of questions.

## Category A

### Observation

What happened?

Example

Shipment delayed.

---

## Category B

### Explanation

Why did it happen?

Example

Inventory mismatch delayed warehouse allocation, which delayed carrier dispatch.

---

## Category C

### Propagation

How did the problem spread?

Example

Inventory mismatch

↓

Warehouse delay

↓

Dispatch delay

↓

Delivery delay

↓

Customer complaint

↓

Revenue impact

---

## Category D

### Counterfactual

What if one event had been different?

Example

If inventory reconciliation occurred within thirty minutes, would delivery still be delayed?

---

## Category E

### Intervention

Which action would have prevented the largest amount of downstream damage at the lowest cost?

---

# 12. Definitions

## Event

A timestamped occurrence that changes the state of the system.

Examples:

Order Created

Inventory Allocated

Package Picked

Shipment Dispatched

Customer Cancelled

---

## Entity

An object participating in events.

Examples:

Order

Warehouse

Supplier

Truck

Employee

Product

Customer

---

## State

The condition of an entity at a specific time.

---

## Transition

A state change caused by an event.

---

## Cause

An event contributing to another event.

---

## Root Cause

The earliest actionable event whose modification could prevent downstream consequences.

---

## Propagation

The transmission of effects through multiple events.

---

## Intervention

An action capable of interrupting a causal chain.

---

## Counterfactual

A hypothetical scenario evaluating what would happen if one or more events changed.

---

# 13. High-Level Product Workflow

Raw Dataset

↓

Data Validation

↓

Entity Identification

↓

Event Extraction

↓

Timeline Construction

↓

State Transition Detection

↓

Causal Candidate Generation

↓

Causal Graph Construction

↓

Propagation Analysis

↓

Root Cause Ranking

↓

Intervention Recommendation

↓

Natural Language Explanation

↓

Interactive Visualization

---

# 14. Success Criteria

The system succeeds if it enables users to answer:

* Why?
* Where?
* When?
* How?
* What if?
* What should be done?

without manually reconstructing operational history.

---

# 15. Product Goals

### Goal 1

Reduce investigation time.

---

### Goal 2

Increase confidence in operational explanations.

---

### Goal 3

Expose recurring structural weaknesses.

---

### Goal 4

Recommend interventions rather than merely reporting failures.

---

### Goal 5

Remain extensible to additional domains.

---

# 16. Non-Goals

The project does not attempt to prove causality with mathematical certainty.

Instead, it reconstructs the most plausible causal explanations supported by:

* temporal ordering,
* process constraints,
* business rules,
* statistical evidence,
* domain knowledge,
* explicit confidence scores.

The distinction between inferred causality and verified causality must always remain visible to users.

---

# 17. Engineering North Star

Every new feature must improve at least one of the following capabilities:

* understanding events,
* explaining events,
* reconstructing causal chains,
* improving intervention quality,
* increasing transparency,
* expanding domain independence.

If a proposed feature improves dashboards but not causal reasoning, it should not be prioritized for the core engine.


# Part II — Canonical Data Model & Causal Intelligence Engine

---

# 18. Engineering Objective

The objective of the Causal Intelligence Engine is to transform flat relational records into a structured, explainable causal knowledge graph.

Traditional analytics treats each row independently.

This system treats each row as evidence of one or more events occurring within a larger process.

The fundamental computational unit is **not a row**.

It is an **Event**.

---

# 19. Engineering Philosophy

Every engineering component must preserve the following transformation:

Raw Data

↓

Events

↓

State Changes

↓

Temporal Graph

↓

Candidate Causes

↓

Causal Graph

↓

Root Cause Analysis

↓

Intervention Recommendation

Every module in the architecture exists to improve one stage of this transformation.

---

# 20. Canonical Data Representation

Regardless of input format, every dataset must eventually be transformed into a universal internal representation.

The engine should never reason directly over CSV rows.

Instead it reasons over standardized objects.

---

## Entity

Represents something that exists.

Examples:

* Order
* Customer
* Warehouse
* Product
* Supplier
* Shipment
* Employee
* Carrier
* Region

Every entity must have:

* Unique ID
* Entity Type
* Attributes
* Lifecycle
* Current State

---

## Event

Represents something that happened.

Every event must contain:

* Event ID
* Timestamp
* Event Type
* Trigger
* Source Entity
* Target Entity
* Changed Attributes
* Metadata
* Confidence

Examples:

Order Created

Inventory Reserved

Inventory Released

Package Picked

Package Packed

Shipment Assigned

Shipment Dispatched

Shipment Delayed

Order Delivered

Order Cancelled

---

## State

Represents an entity's condition immediately after an event.

Examples:

Inventory Available

Inventory Reserved

Inventory Empty

Shipment Waiting

Shipment Moving

Shipment Delayed

Shipment Delivered

---

## Transition

Represents movement between states.

Inventory Available

↓

Inventory Reserved

↓

Inventory Picked

↓

Inventory Shipped

---

# 21. Event Ontology

The engine requires a standardized event vocabulary.

Events fall into several categories.

## Business Events

Order Created

Order Updated

Order Cancelled

Payment Approved

Payment Failed

Customer Complaint

---

## Warehouse Events

Inventory Reserved

Inventory Released

Item Picked

Item Packed

Inventory Shortage

---

## Transportation Events

Carrier Assigned

Vehicle Loaded

Shipment Dispatched

Shipment Delayed

Shipment Delivered

Route Changed

---

## External Events

Holiday

Weather

Traffic

Port Congestion

Fuel Price Spike

Government Restriction

These events may originate outside the DataCo dataset but the architecture must support future integration.

---

# 22. Entity Relationships

The engine must understand structural relationships.

Example

Customer

↓

places

↓

Order

↓

contains

↓

Product

↓

stored in

↓

Warehouse

↓

ships via

↓

Carrier

↓

arrives at

↓

Customer

These relationships remain stable.

Events change their states.

---

# 23. Temporal Model

Time is a hard constraint.

The engine must enforce:

Cause Timestamp

<

Effect Timestamp

No inferred causal edge may violate temporal ordering.

---

# 24. Event Timeline Reconstruction

Rows from the dataset belonging to the same operational process must be grouped.

Example

Order

↓

Payment

↓

Inventory Allocation

↓

Picking

↓

Packing

↓

Dispatch

↓

Transit

↓

Delivery

This ordered sequence becomes the event timeline.

---

# 25. Causal Graph

The internal reasoning structure is a directed graph.

Nodes

Events

Edges

Potential causal influence

Each edge contains:

Source Event

Destination Event

Confidence

Evidence

Propagation Weight

Business Rule Support

Statistical Support

---

Example

Inventory Shortage

↓

Warehouse Delay

↓

Truck Missed

↓

Late Delivery

↓

Customer Complaint

↓

Refund

---

# 26. Types of Causal Edges

The engine distinguishes between edge categories.

### Direct Cause

A directly produces B.

---

### Conditional Cause

A produces B only if condition C exists.

Example

Traffic

↓

Delivery Delay

only if

Road Transport

---

### Contributing Cause

Several causes jointly produce an outcome.

Inventory Shortage

*

High Demand

*

Holiday

↓

Shipment Delay

---

### Amplifying Cause

The event increases downstream impact.

Example

Holiday

↓

Traffic

↓

Delay

---

### Inhibiting Cause

A reduces propagation.

Example

Emergency Inventory

↓

Reduced Delay

---

# 27. Candidate Cause Generation

Every event may have multiple candidate causes.

The engine should initially construct a candidate graph rather than assuming certainty.

Candidate causes are ranked later.

Sources include:

Temporal proximity

Business rules

Shared entities

Shared identifiers

Historical frequency

Domain ontology

Statistical association

---

# 28. Confidence Model

Every inferred edge requires confidence.

Confidence ranges:

0

↓

1

Example

Inventory Shortage

↓

Warehouse Delay

Confidence

0.91

Explanation

Observed together repeatedly

Business rule supports relationship

Correct temporal order

Shared warehouse

---

# 29. Root Cause Analysis

Root cause is defined as:

The earliest actionable event whose modification would prevent the largest amount of downstream impact.

This differs from:

Earliest event

or

Most frequent event.

The distinction is critical.

Example

Storm

↓

Traffic

↓

Late Dispatch

↓

Customer Complaint

The storm may be earliest.

Late Dispatch may be actionable.

The system should distinguish both.

---

# 30. Propagation Analysis

Every downstream consequence should be measured.

Propagation includes:

Depth

Breadth

Duration

Affected entities

Economic impact

Operational impact

Confidence

Example

Inventory Error

↓

Warehouse Delay

↓

Carrier Delay

↓

Late Delivery

↓

Complaint

↓

Refund

↓

Negative Review

Propagation Depth

6

---

# 31. Feedback Loop Detection

Many operational systems contain loops.

Example

Late Delivery

↓

Customer Complaints

↓

Support Overload

↓

Slower Processing

↓

More Delays

The engine must identify such reinforcing cycles.

---

# 32. Intervention Points

Each causal chain should expose intervention opportunities.

Every intervention includes:

Node

Estimated Cost

Expected Benefit

Affected Events

Expected Delay Reduction

Confidence

---

Example

Inventory Verification

Cost

Low

Benefit

High

Propagation Reduced

82%

---

# 33. Counterfactual Engine

The engine must answer hypothetical questions.

Examples

What if shipment left two hours earlier?

What if inventory were available?

What if warehouse capacity increased?

The engine simulates downstream changes without modifying historical records.

---

# 34. Explainability Engine

Every conclusion must be inspectable.

Users should never receive:

Shipment delayed because AI predicted so.

Instead

Shipment delayed because:

Inventory unavailable

↓

Warehouse waiting

↓

Carrier missed pickup window

↓

Dispatch delayed

↓

Delivery delayed

Confidence

91%

Supporting Evidence

Business Rule

Historical Similarity

Temporal Consistency

---

# 35. Domain Independence

No algorithm should reference:

Warehouse

Customer

Shipment

directly.

Algorithms operate on:

Entities

Events

States

Transitions

Relationships

Only the ontology layer understands logistics terminology.

Replacing the ontology should enable another domain without changing the reasoning engine.

---

# 36. Internal Modules

The engine consists of the following logical modules.

Data Adapter

↓

Schema Mapper

↓

Entity Extractor

↓

Event Generator

↓

Timeline Builder

↓

State Engine

↓

Relationship Resolver

↓

Temporal Graph Builder

↓

Candidate Cause Generator

↓

Confidence Scorer

↓

Root Cause Analyzer

↓

Propagation Analyzer

↓

Counterfactual Simulator

↓

Intervention Optimizer

↓

Explanation Generator

↓

Visualization API

Each module has a single responsibility and communicates through standardized interfaces.

---

# 37. Research Constraints

The engine must explicitly distinguish:

Observed Facts

Business Assumptions

Statistical Associations

Inferred Causes

Counterfactual Simulations

These categories must never be conflated in the implementation or the user interface.

---

# 38. Engineering Principles

The implementation must satisfy the following principles:

Deterministic when rules are explicit.

Probabilistic when evidence is incomplete.

Explainable by design.

Extensible through ontology.

Independent of any single dataset.

Modular.

Reproducible.

Inspectable.

Auditable.

---

# 39. Definition of Success

The engine is considered successful if it can transform an arbitrary operational dataset into a causal graph that allows a user to answer:

What happened?

Why did it happen?

Where did it begin?

How did it spread?

Which event mattered most?

What could have prevented it?

What is the lowest-cost intervention?

What would have happened if one event were different?

without manually reconstructing the operational history.


# Part III — Implementation Blueprint, System Architecture & Execution Plan

---

# 40. System Architecture Overview

The platform follows a layered architecture.

```
                    User Interface
                           │
                           ▼
                  Visualization Layer
                           │
                           ▼
                Explanation Engine API
                           │
                           ▼
                 Causal Intelligence Core
                           │
        ┌──────────┬──────────┬──────────┐
        ▼          ▼          ▼
  Graph Engine  ML Engine  Rule Engine
        │          │          │
        └──────────┴──────────┘
                   │
                   ▼
          Temporal Property Graph
                   │
                   ▼
           Data Processing Pipeline
                   │
                   ▼
          Raw Dataset / External APIs
```

Every layer has one responsibility.

---

# 41. Technology Stack

## Frontend

* Next.js
* React
* TypeScript

Visualization

* React Flow
* Cytoscape.js
* D3.js (selected views)

Charts

* Apache ECharts

---

## Backend

* Python
* FastAPI

Reasoning

* NetworkX
* PyTorch Geometric (future)
* pgmpy
* DoWhy (future)

---

## Databases

Relational

PostgreSQL

Graph

Neo4j

Cache

Redis

Object Storage

S3 Compatible Storage

---

## DevOps

Docker

GitHub Actions

NGINX

---

# 42. Why Two Databases?

PostgreSQL stores facts.

Neo4j stores relationships.

Example

PostgreSQL

```
Order 821
Warehouse Delhi
Dispatch Time
```

Neo4j

```
Inventory Shortage

↓

Warehouse Delay

↓

Dispatch Delay
```

Do not force graph reasoning into SQL.

---

# 43. Repository Structure

```
backend/

frontend/

ontology/

graph_engine/

rule_engine/

causal_engine/

counterfactual_engine/

recommendation_engine/

visualization/

tests/

docs/

datasets/

scripts/

deployment/
```

Every directory represents one bounded responsibility.

---

# 44. Backend Services

## Dataset Service

Responsible for

* importing datasets
* schema detection
* validation
* preprocessing

---

## Ontology Service

Maps dataset columns into universal entities.

Example

```
order id

↓

Entity

Order
```

---

## Event Builder

Transforms records into events.

Example

CSV Row

↓

Shipment Assigned Event

---

## Timeline Builder

Groups events by process.

Example

Order

↓

Payment

↓

Packing

↓

Dispatch

↓

Delivery

---

## Graph Builder

Creates the Temporal Property Graph.

No causal inference occurs here.

---

## Causal Engine

Constructs inferred causal edges.

Outputs confidence scores.

---

## Root Cause Engine

Ranks causal nodes.

Produces ranked explanations.

---

## Counterfactual Engine

Generates hypothetical worlds.

---

## Recommendation Engine

Finds optimal interventions.

---

## Explanation Engine

Transforms graph reasoning into human language.

---

# 45. ML Components

Version 1

Rule-assisted reasoning.

Version 2

Bayesian Networks.

Version 3

Graph Neural Networks.

Version 4

Reinforcement Learning.

Version 1 must remain useful without sophisticated ML.

The intelligence comes from architecture rather than model complexity.

---

# 46. Rule Engine

Business rules are explicit.

Example

```
Inventory Empty

↓

Cannot Pick Product
```

Rule syntax should be configurable.

Never hardcode logistics logic into source code.

---

# 47. Graph Database Schema

Node Types

Entity

Event

State

Location

Time

External Event

Recommendation

Intervention

---

Relationship Types

```
CAUSES

PRECEDES

BELONGS_TO

LOCATED_AT

TRANSITIONS_TO

PART_OF

AFFECTS

BLOCKS

AMPLIFIES

REDUCES

RECOMMENDS
```

---

# 48. Processing Pipeline

Dataset

↓

Validation

↓

Cleaning

↓

Schema Mapping

↓

Ontology Mapping

↓

Entity Extraction

↓

Event Generation

↓

Timeline Construction

↓

Temporal Graph

↓

Rule Evaluation

↓

Candidate Causes

↓

Confidence Scoring

↓

Root Cause Ranking

↓

Counterfactual Simulation

↓

Recommendation Generation

↓

Natural Language Explanation

↓

Dashboard

---

# 49. Confidence Score

Every recommendation contains:

```
Overall Confidence

Rule Support

Historical Support

Temporal Support

Statistical Support

Graph Connectivity

Evidence Count
```

Confidence should never be represented by a single unexplained number.

---

# 50. Recommendation Score

Each intervention receives

```
Impact Score

Implementation Cost

Estimated Delay Reduction

Confidence

Affected Orders

Affected Revenue

Operational Risk
```

Ranking function

```
Highest Benefit

Lowest Cost

Highest Confidence
```

---

# 51. User Interface

Dashboard consists of six workspaces.

---

Workspace 1

System Overview

KPIs

Active Events

Delay Statistics

---

Workspace 2

Timeline Explorer

Interactive operational timeline.

---

Workspace 3

Causal Graph Explorer

Interactive graph.

Expandable nodes.

Confidence display.

---

Workspace 4

Root Cause Analysis

Top contributing events.

Propagation tree.

Evidence.

---

Workspace 5

Counterfactual Simulator

Interactive controls.

"What if inventory increased?"

"What if dispatch occurred earlier?"

Graph updates live.

---

Workspace 6

Recommendation Center

Ranked interventions.

Expected improvement.

Cost.

Confidence.

---

# 52. Natural Language Reports

Users should receive explanations similar to:

"The shipment delay originated from an inventory shortage detected at Warehouse W12. Inventory verification occurred two hours later, causing warehouse allocation to miss the scheduled carrier dispatch window. Historical evidence indicates similar chains in 84 previous orders. Earlier inventory reconciliation would likely reduce delivery delay by approximately 11 hours."

Every sentence should correspond to graph evidence.

---

# 53. API Design

Example endpoints

```
POST /dataset/upload

POST /dataset/map

GET /events

GET /timeline/{order}

GET /graph

GET /root-cause/{order}

GET /counterfactual

GET /recommendations

GET /report/{order}
```

All APIs return structured JSON.

---

# 54. Security

Role-based access.

Audit logging.

Dataset versioning.

Immutable event history.

Recommendation traceability.

No inferred result should overwrite observed facts.

---

# 55. Performance Goals

Dataset loading

< 30 seconds

Graph generation

< 60 seconds

Root cause query

< 3 seconds

Counterfactual query

< 5 seconds

Recommendation generation

< 5 seconds

These targets apply to Version 1 using the DataCo dataset.

---

# 56. Testing Strategy

Unit Tests

Every module.

Integration Tests

Pipeline execution.

Graph Tests

Edge correctness.

Timeline correctness.

Ontology mapping.

Counterfactual consistency.

UI Tests

Interactive graph.

API Tests

Response validation.

---

# 57. Evaluation Metrics

Traditional metrics are insufficient.

Evaluate using

Graph completeness.

Root cause localization accuracy.

Propagation accuracy.

Explanation consistency.

Recommendation usefulness.

Average investigation time reduction.

Counterfactual plausibility.

User trust.

---

# 58. Future Extensions

Streaming event processing.

IoT integration.

Live ERP connectors.

Knowledge graph federation.

Large Language Model explanation refinement.

Digital twins.

Autonomous intervention planning.

Cross-company causal analysis.

Multi-agent optimization.

---

# 59. Risks

Incomplete timestamps.

Missing events.

Conflicting business rules.

Noisy data.

Hidden confounders.

Correlation mistaken for causation.

Ontology mismatch.

These risks must be explicitly surfaced to users.

---

# 60. Research Contributions

If implemented successfully, the project contributes:

A reusable event ontology.

A domain-independent causal reasoning engine.

A temporal property graph framework.

An explainable intervention recommendation engine.

A configurable ontology layer for cross-domain deployment.

A foundation for future causal AI systems.

---

# 61. Product Completion Criteria

Version 1 is complete when a user can:

Import the DataCo dataset.

Automatically generate entities and events.

Construct operational timelines.

Visualize the Temporal Property Graph.

Infer probable causal chains.

Inspect confidence and supporting evidence.

Identify ranked root causes.

Run counterfactual scenarios.

Receive intervention recommendations.

Generate explainable reports.

without writing code.

---

# 62. Final Architectural Principle

This project is **not** a logistics dashboard.

It is **not** a predictive analytics platform.

It is **not** a machine learning model that predicts delays.

It is a **Causal Intelligence Platform** whose first implementation happens to use logistics data.

The engine must always reason over:

Events

↓

State Transitions

↓

Relationships

↓

Time

↓

Evidence

↓

Causality

The domain is replaceable.

The reasoning engine is not.

---

# Appendix A — Canonical Processing Lifecycle

```
Raw Dataset
      │
      ▼
Schema Validation
      │
      ▼
Ontology Mapping
      │
      ▼
Entity Extraction
      │
      ▼
Event Generation
      │
      ▼
Timeline Reconstruction
      │
      ▼
Temporal Property Graph
      │
      ▼
Candidate Cause Generation
      │
      ▼
Causal Graph Inference
      │
      ▼
Propagation Analysis
      │
      ▼
Root Cause Ranking
      │
      ▼
Counterfactual Simulation
      │
      ▼
Intervention Optimization
      │
      ▼
Natural Language Explanation
      │
      ▼
Interactive User Interface
```

---

# Appendix B — Design Doctrine

Every feature added to the platform must satisfy at least one of these objectives:

* Improve understanding of operational events.
* Improve causal inference quality.
* Improve explanation quality.
* Improve intervention quality.
* Increase domain independence.
* Increase transparency and auditability.

If a feature does not advance one of these objectives, it should not be part of the core platform.
