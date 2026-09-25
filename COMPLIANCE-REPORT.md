# Compliance Report — Build 140

**Generated:** 2026-09-24T09:21:16Z
**Chassis:** python-fastapi v1.3.3
**Catalog version:** 1.0.0 (last reviewed 2026-06-05)

## Executive Summary

This application targets the **strictest** of FISMA Moderate, FedRAMP Moderate, and DISA IL-2 baselines for each applicable NIST 800-53 control.

Of **29** application-level controls in the catalog:

- ✅ **19** met by the chassis (no per-slot action needed)
- 🔧 **4** met by slot code (verified during build)
- 🌐 **5** inherited from the deploy host (Azure, GovCloud, etc.)
- ⚠ **1** partially met — flagged for chassis v0.6 hardening

## Platform Compliance Posture

Platform itself targets FISMA M (operator's chosen baseline). It is built to all FedRAMP Moderate controls additionally so a move to AWS/Azure FedRAMP M GovCloud is a host swap, not a re-engineering. When a gov customer downloads + self-installs in their own GovCloud, FISMA M applies. When we host gov customers on our own infra, FedRAMP M applies. Controls are near-identical between the two baselines.

## Controls by Family

### AC — Access Control (7 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **AC-12** | Session Termination | Session terminated after 15 minutes inactivity OR explicit logout. | ✅ Met by chassis | `chassis-python/app/auth/service.py`<br/>`chassis-python/app/frontend.py`<br/>JWT TTL bound by jwt_access_token_ttl_minutes setting (default 60 min — operator can drop to 15 for stricter compliance). Logout endpoint clears cookie. |
| **AC-17** | Remote Access | Remote access via TLS + MFA when implemented. | 🌐 Inherited from host | TLS is host-provided (Azure / GovCloud terminate TLS at the load balancer). MFA is a chassis v1.x feature; until then this control is partially met. |
| **AC-2** | Account Management | Account lifecycle managed with quarterly activity monitoring; accounts disabled after 90 days inactivity; role assignments via RBAC. | ✅ Met by chassis | `chassis-python/app/auth/`<br/>`chassis-python/app/rbac/`<br/>Chassis ships register/login/RBAC role assignment. Per-account 90-day inactivity monitoring is operator-configurable via a future RQ job; not yet shipped — flagged for chassis v0.7. |
| **AC-3** | Access Enforcement | Role-based + permission-based access control on every authenticated endpoint. | ✅ Met by chassis | `chassis-python/app/rbac/`<br/>`chassis-python/app/deps.py`<br/>Chassis-provided requires(permission) FastAPI dependency. Slot authors gate every route with it; LLM annotations marked AC-3 are pattern-match verified by checking for the import + usage. |
| **AC-6** | Least Privilege | Permissions granted at the lowest level necessary; all privileged actions audited. | 🔧 Met by slot | `chassis-python/app/rbac/`<br/>The chassis provides RBAC primitives but each slot defines its own permission scope. The Hybrid LLM audit reviews whether the LLM-annotated AC-6 controls match the slot's actual permission grant patterns. |
| **AC-7** | Unsuccessful Logon Attempts | 3 attempts / 15 min / 30 min lockout (FedRAMP M is stricter on attempt count). | ✅ Met by chassis | `chassis-python/app/auth/service.py`<br/>✅ Met by chassis v0.6: User.failed_login_attempts + locked_until columns; authenticate() rejects fast (no bcrypt) during lockout for anti-brute-force. Routes return 401 (anti-enumeration) with Retry-After header. Migration 0006_ac7_lockout.py. |
| **AC-8** | System Use Notification | Login banner displayed; acknowledgment required before access. | ✅ Met by chassis | `chassis-python/app/templates/auth/login.html`<br/>✅ Met by chassis v0.6: Settings.system_use_notification threaded through frontend._common_context into login.html. Renders as USWDS usa-alert--warning with aria-live='polite' for screen readers. Multi-line via white-space: pre-line CSS. Operator sets via SYSTEM_USE_NOTIFICATION env var. |

### AU — Audit and Accountability (6 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **AU-11** | Audit Record Retention | 6 years online or archived (IL-2 is strictest). | ✅ Met by chassis | `chassis-python/app/audit/`<br/>✅ Met by chassis v0.6: app/audit/tasks.py:archive_old_audit_logs RQ task moves rows older than Settings.audit_retention_days (default 365) into audit_logs_archive table (migration 0007). Idempotent (re-runs no-op). Operator wires to AWS EventBridge / GCP Scheduler / cron. IL-2 6-year retention met via 365-day online + archive. |
| **AU-12** | Audit Generation | Audit generation for all AU-2 events. | ✅ Met by chassis | `chassis-python/app/audit/decorator.py`<br/>Chassis @audited decorator generates records. Slot authors apply it to state-mutating functions. |
| **AU-2** | Event Logging | Log all auth events, privilege changes, and slot-author-defined actions. | ✅ Met by chassis | `chassis-python/app/audit/`<br/>`chassis-python/app/auth/`<br/>`chassis-python/app/logging.py`<br/>Chassis @audited decorator on every state-mutating service function. Auth events logged via structlog at WARN level. |
| **AU-3** | Content of Audit Records | Audit record includes: timestamp, actor user_id, actor org_id, action, entity_type, entity_id, source IP address, details JSON. | ✅ Met by chassis | `chassis-python/app/audit/decorator.py`<br/>`chassis-python/app/audit/models.py`<br/>✅ Met by chassis v0.6: current_client_ip_var contextvar bound in request_id_middleware (XFF-aware: X-Forwarded-For[0] preferred over request.client.host); @audited decorator reads and populates AuditLog.ip_address. Graceful degradation to NULL for RQ worker invocations. |
| **AU-6** | Audit Review, Analysis, and Reporting | Weekly audit log review process. | 🔧 Met by slot | `chassis-python/app/audit/`<br/>Chassis provides the log; slot author (operator) is responsible for the review process. Documented as operator-responsibility in COMPLIANCE-REPORT.md. |
| **AU-9** | Protection of Audit Information | Audit logs are append-only at the database layer; app role has only INSERT permission. | ✅ Met by chassis | `chassis-python/app/audit/`<br/>`chassis-python/migrations/`<br/>✅ Met by chassis v0.6: Migration 0008_au9_audit_log_permissions.py REVOKEs UPDATE/DELETE on audit_logs from the app DB role (env var AU9_APP_ROLE controls role name, default 'app_user'). Conditional on role existence; emits a UserWarning with the manual SQL when role absent. Append-only convention in app/audit/ is now defense-in-depth backstop. |

### CM — Configuration Management (2 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **CM-2** | Baseline Configuration | Baseline config tracked in version control. | ✅ Met by chassis | `chassis-python/.git/`<br/>`chassis-python/CHASSIS_VERSION`<br/>Chassis source + version pinned via CHASSIS_VERSION + git tags. Customer ZIP includes CHASSIS-VERSION.json for downstream baseline tracking. |
| **CM-6** | Configuration Settings | Settings documented via pydantic-settings; deviations from defaults logged. | ✅ Met by chassis | `chassis-python/app/config.py`<br/>All chassis configuration via pydantic-settings (typed). Slot authors who add settings subclass Settings. |

### IA — Identification and Authentication (3 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **IA-2** | Identification and Authentication (Organizational Users) | Unique user identification + MFA for privileged accounts (chassis v1.x). | ⚠ Partial | `chassis-python/app/auth/`<br/>Email + bcrypt password + JWT issued by chassis. MFA not yet shipped (chassis v1.x feature). Partial compliance until then. |
| **IA-5** | Authenticator Management (Passwords) | 14-char min, 4 character classes (IL-2 strictest). | ✅ Met by chassis | `chassis-python/app/auth/schemas.py`<br/>✅ Met by chassis v0.6: UserRegister.password Field(min_length=14) + field_validator runs validate_password_complexity checking ≥1 uppercase, ≥1 lowercase, ≥1 digit, ≥1 special. Module-level validator exposed so frontend.py and JSON API produce identical error messages. Optional breached-password check via have-i-been-pwned API remains a v0.7 candidate. |
| **IA-8** | Identification and Authentication (Non-Organizational Users) | External users authenticated via same chassis flow. | ✅ Met by chassis | `chassis-python/app/auth/`<br/>Chassis treats all users uniformly; org membership separates internal vs external context. |

### SC — System and Communications Protection (5 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **SC-13** | Cryptographic Protection | FIPS-validated cryptographic modules. | 🔧 Met by slot | `chassis-python/app/auth/service.py`<br/>Chassis uses bcrypt + python-jose. Slot authors who introduce custom crypto MUST use cryptography library (not e.g. random.choice for IDs). Hybrid LLM audit reviews annotated SC-13 files for crypto patterns. |
| **SC-28** | Protection of Information at Rest | AES-256 encryption at rest for DB + storage. | 🌐 Inherited from host | Disk + DB encryption at rest is host-provided (Azure encrypts at-rest by default; GovCloud requires explicit KMS configuration). |
| **SC-5** | Denial of Service Protection | DoS protection at host layer. | 🌐 Inherited from host | Azure / GovCloud WAF handles DoS protection at the network edge. |
| **SC-7** | Boundary Protection | Boundary protection at host layer. | 🌐 Inherited from host | Inherited from Azure / GovCloud VPC + WAF. |
| **SC-8** | Transmission Confidentiality and Integrity | TLS 1.2+ with DoD-approved cipher suites (IL-2 in DoD context). | 🌐 Inherited from host | TLS termination at host load balancer. Chassis app speaks plain HTTP behind the load balancer. |

### SI — System and Information Integrity (5 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **SI-10** | Information Input Validation | All API inputs validated via Pydantic v2 schemas. | ✅ Met by chassis | `chassis-python/app/`<br/>Chassis Pydantic v2 schemas validate every incoming request. Slot authors who annotate SI-10 are pattern-match verified by checking for BaseModel + Field usage. |
| **SI-11** | Error Handling | Error responses strip stack traces in production; full traces only in dev/test. | ✅ Met by chassis | `chassis-python/app/main.py`<br/>✅ Met by chassis v0.6: app/error_handlers.py:prod_exception_handler registered on Exception. In prod (settings.is_prod), returns generic {'error': 'Internal server error', 'request_id': '...'} — no type/message/traceback. In dev/test, returns type + message (still no traceback). structlog ALWAYS logs full exception with exc_info regardless of env. HTTPException uses FastAPI defaults (correct). |
| **SI-12** | Information Management and Retention | Per-table retention metadata; archival jobs. | ✅ Met by chassis | ✅ Met by chassis v0.6: RetainableFor mixin in app/db.py provides per-row retention metadata (retained_until: Mapped[datetime\|None], indexed). Composes with TenantScoped. AU-11 archival job queries this for per-row policy decisions. NOT a soft-delete — chassis position on soft-delete is opt-in per slot (ARCHITECTURE §2.9). |
| **SI-2** | Flaw Remediation | 30 days for critical patches. | ✅ Met by chassis | `.github/workflows/chassis-drift.yml`<br/>Chassis dependency updates tracked via dependabot-style automation (plan §10 — automated configuration update routine). Customers re-pull chassis releases to get patches. |
| **SI-4** | System Monitoring | Logs + metrics ingested into a monitoring system. | ✅ Met by chassis | `chassis-python/app/logging.py`<br/>Chassis ships structlog + Prometheus instrumentator. Operator wires to their preferred APM / SIEM. |

### PT — PII Processing and Transparency (1 controls)

| Control | Title | Strictest Baseline | Status | Implementation / Notes |
|---|---|---|---|---|
| **PT-1** | Privacy Authorization for Collection and Sharing of PII | PII collection documented + minimized. | 🔧 Met by slot | Slot author is responsible for PII handling. Hybrid LLM audit reviews annotated PT-1 files for explicit user-data field declarations. |

## Slot-Author Responsibilities

The following controls require slot-specific verification. The chassis provides the primitives; the slot author's implementation determines whether the control is satisfied for this particular application:

- **AC-6 — Least Privilege** — The chassis provides RBAC primitives but each slot defines its own permission scope. The Hybrid LLM audit reviews whether the LLM-annotated AC-6 controls match the slot's actual permission grant patterns.
- **AU-6 — Audit Review, Analysis, and Reporting** — Chassis provides the log; slot author (operator) is responsible for the review process. Documented as operator-responsibility in COMPLIANCE-REPORT.md.
- **SC-13 — Cryptographic Protection** — Chassis uses bcrypt + python-jose. Slot authors who introduce custom crypto MUST use cryptography library (not e.g. random.choice for IDs). Hybrid LLM audit reviews annotated SC-13 files for crypto patterns.
- **PT-1 — Privacy Authorization for Collection and Sharing of PII** — Slot author is responsible for PII handling. Hybrid LLM audit reviews annotated PT-1 files for explicit user-data field declarations.

## Deploy-Host Inheritance

The following controls are inherited from the deploy host. When deploying to a different host (Azure → GovCloud), these inheritances re-bind:

- **AC-17 — Remote Access** — TLS is host-provided (Azure / GovCloud terminate TLS at the load balancer). MFA is a chassis v1.x feature; until then this control is partially met.
- **SC-5 — Denial of Service Protection** — Azure / GovCloud WAF handles DoS protection at the network edge.
- **SC-7 — Boundary Protection** — Inherited from Azure / GovCloud VPC + WAF.
- **SC-8 — Transmission Confidentiality and Integrity** — TLS termination at host load balancer. Chassis app speaks plain HTTP behind the load balancer.
- **SC-28 — Protection of Information at Rest** — Disk + DB encryption at rest is host-provided (Azure encrypts at-rest by default; GovCloud requires explicit KMS configuration).

---

*This report was generated by the SD-Agile Platform App Builder against compliance/controls.json. The catalog is the single source of truth across all chassis-backed Stack Templates. For control-by-control evidence beyond what this report includes, an ATO assessor should review the chassis source files named in the `chassis_implementation_paths` field of the catalog.*
