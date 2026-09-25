---
template: python-solicitation
version: "3.0"
document_type: SOLICITATION.md
locked_section_aware: true
---

# {{PROJECT_NAME}} — Solicitation Package (RFP)
<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: true -->
## Custom Application Build Solicitation (Python 3.12 · FastAPI · SQLAlchemy 2.0 · PostgreSQL)

**Project:** {{PROJECT_NAME}}
**Target Platform:** Custom FastAPI application (async FastAPI/Uvicorn · SQLAlchemy 2.0/Alembic on PostgreSQL · Redis · server-rendered Jinja2 + vendored USWDS 3.0 · Section 508 / WCAG 2.1 AA)
**Generated From:** REQUIREMENTS.md + DESIGN.md + SPECIFICATION.md + the Golden Record
**Generated Date:** {{DATE}}
**Document Status:** Derived (system-synthesized at finalization)

**Purpose.** This is a complete, standalone **Solicitation Package** a government agency or regulated enterprise can publish as a Request for Proposal (RFP) to procure the build of {{PROJECT_NAME}}. It pairs with `SPECIFICATION.md` to give bidders enough detail to produce high-quality, comparable proposals, and to give the buyer **finite, measurable** acceptance and performance specifications to manage the awarded vendor. Every requirement statement is synthesized from the project's REQUIREMENTS/DESIGN/SPECIFICATION and Golden Record — it introduces no new requirement, only structures the existing ones for procurement. Sections marked *(buyer to complete)* hold procurement-specific facts (dates, contract type, agency-specific clauses) the issuing organization fills in before release.

---

<!-- @owned-by: phase2_as_is_discovery | @role: business | @system-derives-from: Golden Record (Current State — AS-IS Discovery, Org Context) | @locked-by-chassis: false -->
## 1. Background & Organizational Context

*The issuing organization's mission context, the current state (AS-IS) systems and pain points, and why this initiative exists. Establishes the operational backdrop a bidder needs to scope the work. Synthesized from the AS-IS discovery phase and the Golden Record's org context.*

---

<!-- @owned-by: phase3_to_be_imagineering | @role: business | @system-derives-from: Golden Record (TO-BE Imagineering — Future Process Design) | @locked-by-chassis: false -->
## 2. Objectives & Desired Outcomes

*The business outcomes the delivered application must achieve, expressed as outcomes (not implementation). Each objective is stated so its achievement can be objectively assessed at acceptance. Synthesized from the TO-BE phase.*

---

<!-- @owned-by: phase5_requirements_enumeration | @role: business | @system-derives-from: REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR) | @locked-by-chassis: false -->
## 3. Scope Boundary Statement

*What is explicitly IN scope and OUT of scope, so the work is bounded for fixed-scope bidding.*

**In scope (bid as new development):** the project's functional requirements (REQUIREMENTS §3, FR-prefixed) realized as domain slots (`app/slots/<domain>/`) — models, Pydantic v2 schemas, services, `APIRouter` endpoints, Jinja2/USWDS screens, and the Alembic migrations that add the new tables. Any explicit `(CHASSIS-OVERRIDE)` requirement noted in REQUIREMENTS §5 is also bid work.

**Out of scope (Python-chassis foundation — inherited baseline, NOT bid as new development):** the Platform-Provided Foundation enumerated in REQUIREMENTS §2 — identity & authentication (including mandatory TOTP MFA), RBAC authorization, multi-tenancy/organization management, audit & accountability (including AU-11 archival), the administration shell, observability/health endpoints, in-app documentation, the embedded LLM capability, file storage, notifications, rate limiting, reporting, transactional email and background jobs, and the accessible Jinja2 + USWDS frontend shell. These capabilities are already implemented, secured, and tested in the `autonomous-platform-chassis-python` foundation and are delivered to the vendor as a working baseline — the vendor builds slots *on* this baseline, not a replacement for it.

State clearly in the released solicitation whether the chassis foundation source is provided to the awarded vendor (recommended) or must be independently reproduced by the vendor (only if the chassis cannot be delivered under the procurement's licensing terms — buyer to confirm).

---

<!-- @owned-by: phase4_user_personas | @role: business | @system-derives-from: Golden Record (User Personas & Actor Classes) | @locked-by-chassis: false -->
## 4. User Classes, Volumes & Access

*Each user class (from the Golden Record's User Personas capture): description, expected count, frequency of use, privilege level (RBAC role), and access channel. Drives the bidder's sizing/licensing/staffing estimates and the buyer's concurrency acceptance targets.*

---

<!-- @owned-by: phase5_requirements_enumeration | @role: business | @system-derives-from: REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR), DESIGN.md#7. API CONTRACTS (FASTAPI) | @locked-by-chassis: false -->
## 5. Functional Requirements (Performance Work Statement)

*The full, numbered functional requirement set the vendor must deliver, each expressed as a required capability with an objectively verifiable outcome (the PWS core). For every FR: ID, the required capability in outcome terms, the actor(s), and the acceptance condition that proves it is met. Reference `SPECIFICATION.md` §4 for full per-FR detail so bidders can respond requirement-by-requirement. No requirement may be summarized away.*

| FR ID | Required Capability (outcome) | Actor(s) | Acceptance Condition |
|---|---|---|---|

---

<!-- @owned-by: phase5c_technical_architecture | @role: tech | @system-derives-from: DESIGN.md#2. SYSTEM OVERVIEW, DESIGN.md#6. INTEGRATION LAYER (APPLICATION → EXTERNAL SERVICES), CONSTITUTION.md#1. Immutable Technology Stack | @locked-by-chassis: false -->
## 6. Technical & Integration Requirements

*The mandatory technical environment and integration scope the vendor must satisfy: the locked stack (Python 3.12, FastAPI 0.115 on Uvicorn, async SQLAlchemy 2.0 / Alembic on PostgreSQL, Redis for jobs/rate-limiting, server-rendered Jinja2 + vendored USWDS, no SPA/bundler), the layered/slot architecture (DESIGN's Chassis Architecture & Realization section + §2), each external system/interface and its data-exchange contract (DESIGN §6, async `httpx` transport), data-migration volume/complexity, and hosting/containerization constraints (Docker). State which constraints are mandatory ("MUST") versus advisory.*

---

<!-- @owned-by: phase5b_security_requirements | @role: business | @system-derives-from: REQUIREMENTS.md#5. NON-FUNCTIONAL REQUIREMENTS (NFR) (security deltas), CONSTITUTION.md#3. Security Invariants (binding) | @locked-by-chassis: false -->
## 7. Security, Privacy & Compliance Requirements

*The binding security baseline (CONSTITUTION §3 Security Invariants: JWT auth, bcrypt password storage, RBAC, append-only/immutable audit log with AU-11 archival, AES-256-GCM encryption at rest for LLM provider keys, tenant isolation, anti-enumeration, account lockout) plus the project-specific regime (REQUIREMENTS §5 deltas — e.g. FedRAMP/StateRAMP impact level, FISMA-Moderate control families AC-7/IA-5/IA-6/AU-3/AU-9/AU-11/SC-13/SI-11/SI-12, HIPAA/PCI/CJIS/IRS-1075, data residency). Each control stated as a mandatory, testable requirement the vendor must evidence. **Section 508 / WCAG 2.1 AA accessibility is mandatory** and is an acceptance gate.*

---

<!-- @owned-by:  | @role: system | @system-derives-from: REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR), SPECIFICATION.md#9. Verification & Acceptance, TEST-SCENARIOS.md | @locked-by-chassis: false -->
## 8. Deliverables, Tasks & Milestones (Statement of Work)

*Discrete, contractible tasks and deliverables derived from the requirement set and design. Logical implementation phases (no fixed dates unless the buyer sets them). For each deliverable: what is delivered, the form (running application, source, Alembic migrations, `pytest` test suite, SPECIFICATION/operations docs, accessibility audit, security evidence), and the milestone that gates payment/acceptance.*

| # | Deliverable | Description | Acceptance Gate | Milestone |
|---|---|---|---|---|

---

<!-- @owned-by:  | @role: system | @system-derives-from: REQUIREMENTS.md#2.17 Non-Functional Baselines (inherited), REQUIREMENTS.md#5. NON-FUNCTIONAL REQUIREMENTS (NFR) (deltas only), SPECIFICATION.md#7. Non-Functional Requirements | @locked-by-chassis: false -->
## 9. Performance Standards & Service Levels (FINITE & MEASURABLE)

*The objective, measurable standards each deliverable and the running system must meet — the buyer's instrument for managing the vendor. Every standard MUST be finite and measurable (a number + a measurement method), never aspirational prose. Synthesized from the inherited baselines and project NFR deltas.*

| Standard | Metric | Target (measurable) | Measurement Method | Acceptable Range / Penalty Basis |
|---|---|---|---|---|
| Page load (broadband) | p95 latency | ≤ 1.0 s | synthetic + RUM over the acceptance window | … |
| Page load (slow mobile) | p95 latency | ≤ 2.5 s | throttled synthetic | … |
| API reads | p95 latency | ≤ 250 ms | load test at target concurrency | … |
| API writes | p95 latency | ≤ 800 ms | load test at target concurrency | … |
| Availability | monthly uptime | ≥ 99.5% | `/readyz` readiness-probe monitoring | … |
| Concurrency | sessions/instance | ≥ 100 | sustained load test (async Uvicorn workers) | … |
| Accessibility | WCAG 2.1 AA | 0 Level-A/AA violations | automated + manual audit | … |
| Test coverage | line coverage | ≥ [buyer target]% | `pytest --cov` (pytest-cov) report | … |
| Defect density at acceptance | open Sev-1/Sev-2 | 0 / [buyer cap] | acceptance test log | … |

*Each FR also carries its own acceptance condition (§5); the vendor is measured against the union of §5 conditions and the §9 standards.*

---

<!-- @owned-by:  | @role: system | @system-derives-from: SPECIFICATION.md#9. Verification & Acceptance, REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR) | @locked-by-chassis: false -->
## 10. Acceptance Criteria & Verification Method

*How the buyer will verify acceptance: the running application passes the full TEST-SCENARIOS suite (`pytest` + `pytest-asyncio` via FastAPI's `TestClient`/`httpx.AsyncClient`); every FR demonstrably meets its §5 acceptance condition; the §9 performance standards are met under the stated measurement methods; the §7 security controls are evidenced; the accessibility audit passes; documentation deliverables are complete and standalone. State the acceptance procedure, the test environment, who witnesses, and the remediation/re-test process for any failed criterion.*

---

<!-- @owned-by:  | @role: system | @system-derives-from: REQUIREMENTS.md#3. FUNCTIONAL REQUIREMENTS (FR), DESIGN.md#2. SYSTEM OVERVIEW | @locked-by-chassis: false -->
## 11. Evaluation Criteria (How Proposals Will Be Scored)

### 11.1 Technical Approach Factors
*How bidder technical approaches will be scored against the required capabilities (§5) and technical/integration requirements (§6): completeness of requirement coverage, soundness of the architecture against the mandated stack, integration approach, security approach, accessibility approach.*

### 11.2 Management, Staffing & Past-Performance Factors
*Delivery methodology, staffing plan and key personnel qualifications, project management/risk approach, and relevant past performance on comparable Python/FastAPI or regulated builds.*

### 11.3 Cost / Price Factors
*Pricing structure (fixed-price preferred for fixed-scope; T&M ceilings if applicable), cost realism, and total cost of ownership. (buyer to complete: weighting and basis of award.)*

### 11.4 Scoring Method
*The point allocation/weighting across §11.1–§11.3 and the basis for award (best value / lowest price technically acceptable). (buyer to complete.)*

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: false -->
## 12. Proposal Submission Requirements

*What bidders must submit and in what format: a requirement-by-requirement response to §5 (using `SPECIFICATION.md` §4 as the response template), technical narrative, management/staffing volume, past-performance references, and a priced volume. Page limits, format, due date, point of contact, and questions/clarification process. (Procurement-specific fields are buyer to complete.)*

---

<!-- @owned-by:  | @role: system | @system-derives-from:  | @locked-by-chassis: false -->
## 13. Terms, Conditions & Assumptions

### 13.1 Contractual Terms
*(buyer to complete)* — contract type, period of performance, IP/data-rights, warranty, change-control, and any agency-mandated clauses.

### 13.2 Assumptions
*Assumptions carried from the Golden Record and synthesis (e.g., the Python chassis foundation is provided; external systems are available in the integration environment; data-migration source access is granted). Each flagged for buyer confirmation.*

### 13.3 Definitions & Acronyms
*Domain and technical terms used in this package (slot, tenant, RBAC, USWDS, Alembic revision, the compliance acronyms).*

---

*This document was generated by the SD-Agile Spec Builder from the project's Golden Record, on the autonomous-platform-chassis-python foundation. It is a derived, standalone solicitation package — it structures existing requirements for procurement; it does not introduce new ones. Sections marked (buyer to complete) require the issuing organization's procurement-specific input before release.*
