# Security Self-Audit — FISMA Moderate

**System:** applications built on the autonomous-platform Python chassis (Stack Template #1)
**Baseline:** NIST SP 800-53 Rev. 5 — **FISMA Moderate** impact level
**Scope:** the **chassis** controls inherited by every generated application. Application
("slot") code is **out of scope** here and must be assessed separately by the team that
builds it.
**Status:** self-assessment, not an independent audit or an ATO. It documents which control
requirements the chassis satisfies in code, which it partially satisfies, and which are the
**operator's responsibility** to complete in the deployment environment.

> **How to read this.** Each row gives a NIST 800-53 control, the chassis's implementation
> status, and the evidence (file or mechanism). Statuses:
> **✅ Implemented** — satisfied in chassis code. **◐ Partial** — chassis provides the
> mechanism; operator configuration completes it. **▢ Operator** — an organizational or
> environmental control the chassis cannot satisfy alone (deployment, policy, monitoring).

---

## 1. Summary

The chassis directly implements a meaningful subset of the technical controls in the
Access Control (AC), Audit and Accountability (AU), Identification and Authentication (IA),
System and Communications Protection (SC), and System and Information Integrity (SI)
families. Management, operational, and physical controls (CA, CM, CP, IR, MA, MP, PE, PL,
PS, RA, SA) are largely **operator responsibilities** discharged through the deployment
environment and organizational policy.

| Family | Implemented (✅/◐) | Operator (▢) |
|---|---|---|
| AC — Access Control | AC-2, AC-3, AC-7, AC-8, AC-12 | AC-1, AC-6 (policy), AC-17 |
| AU — Audit & Accountability | AU-2, AU-3, AU-8, AU-9, AU-11, AU-12 | AU-1, AU-6 (review) |
| IA — Identification & Authentication | IA-2, IA-5, IA-6, IA-8 | IA-1, IA-4 (lifecycle) |
| SC — System & Comms Protection | SC-5(◐), SC-8(◐), SC-12(◐), SC-13, SC-23, SC-28(◐) | SC-7 |
| SI — System & Information Integrity | SI-10, SI-11, SI-12 | SI-2, SI-3, SI-4, SI-7 |

---

## 2. Access Control (AC)

| Control | Status | Evidence / Notes |
|---|---|---|
| **AC-2 Account Management** | ✅ | Admin shell creates, deactivates, and reactivates users (`app/admin/`); accounts have an explicit `is_active` flag enforced at login. Org admins are scoped to their org. |
| **AC-3 Access Enforcement** | ✅ | RBAC permission checks (`app/rbac/service.py:user_has_permission`) gate every privileged route; the admin shell is gated on `users:write`. The MCP server connection admin screen (`/admin/mcp`) is gated on `mcp:write` the same way, and every enable/disable/delete route additionally re-resolves the target connection scoped to the caller's own organization — a cross-org id never modifies another org's row. |
| **AC-6 Least Privilege** | ◐ | Two seeded roles (`user` read-only, `admin`). Colon-scoped permissions allow finer grants. Defining minimal app-specific roles is the operator/slot author's task. |
| **AC-7 Unsuccessful Logon Attempts** | ✅ | Account lockout: 3 failed logins within a 15-minute window → 30-minute lockout, enforced **before** bcrypt verification (`app/auth/service.py`). Locked accounts return the same message as bad credentials (anti-enumeration). |
| **AC-8 System Use Notification** | ◐ | Login page renders a configurable system-use banner from `settings.system_use_notification` (`app/frontend.py`, `app/config.py`). Operator supplies the approved warning text via env var. |
| **AC-12 Session Termination** | ✅ | JWT access tokens are short-lived (default 60 min, `jwt_access_token_ttl_minutes`); the session cookie expiry matches. Sign-out clears the cookie immediately. |
| **AC-17 Remote Access** | ▢ | TLS termination, VPN, and IP allow-listing are deployment-environment controls. |

---

## 3. Audit and Accountability (AU)

| Control | Status | Evidence / Notes |
|---|---|---|
| **AU-2 Event Logging** | ✅ | Privileged mutations are recorded via the `@audited` decorator (`app/audit/decorator.py`) into the `audit_logs` table (`app/audit/models.py`). |
| **AU-3 Content of Audit Records** | ✅ | Each record captures actor (`user_id`), tenant (`organization_id`), action, entity type/id, details, **client IP** (`app/deps_context.py`, bound by request middleware), and timestamp. |
| **AU-8 Time Stamps** | ✅ | Audit records use timezone-aware UTC timestamps (`created_at`). |
| **AU-9 Protection of Audit Information** | ◐ | Audit writes go through a single decorator path; the archive table is separate. Database-level access restriction and backup integrity are operator responsibilities. |
| **AU-11 Audit Record Retention** | ✅ | Archival job `move_old_audit_logs_to_archive` (`app/audit/tasks.py`) moves rows older than `audit_retention_days` (default 365) into `audit_logs_archive` (migration `0007_au11_archive_logs`), supporting the 6-year online-or-archived requirement. Operator schedules the job and sets long-term retention. |
| **AU-12 Audit Generation** | ✅ | Audit generation is centralized and on by default for chassis admin actions; slots reuse the same decorator. |
| **AU-6 Audit Review/Analysis** | ▢ | Periodic human review and SIEM forwarding are operational controls. The `audit:read` permission exists to support tooling. |

---

## 4. Identification and Authentication (IA)

| Control | Status | Evidence / Notes |
|---|---|---|
| **IA-2 Identification & Authentication (Org Users)** | ✅ | Email + password authentication issuing signed JWTs (`app/auth/service.py`). |
| **IA-5 Authenticator Management** | ✅ | Password complexity policy: ≥14 characters and 4 character classes (upper, lower, digit, special) (`app/auth/schemas.py:validate_password_complexity`). Passwords stored as **bcrypt** hashes (cost 12, `bcrypt_rounds`). |
| **IA-6 Authentication Feedback** | ✅ | Login failures return a uniform "Invalid email or password" message regardless of whether the email exists or the account is locked (anti-enumeration). |
| **IA-8 Identification (Non-Org Users)** | ◐ | Same auth path applies. External federated identity (OAuth/SSO) is a documented v2+ extension point (`app/auth/providers/`). |
| **IA-2(1) MFA** | ▢ | Multi-factor authentication is not implemented in the chassis; operators requiring MFA integrate it at the identity provider or via a slot. **Gap for FISMA Moderate — see §7.** |

---

## 5. System and Communications Protection (SC)

| Control | Status | Evidence / Notes |
|---|---|---|
| **SC-5 Denial of Service Protection** | ◐ | Account lockout limits credential-stuffing; an **opt-in Redis fixed-window per-client rate limiter** (`app/ratelimit/`, `RATE_LIMIT_ENABLED`) caps request volume at the app edge. Edge/network DoS protection remains a deployment-layer control. |
| **SC-8 Transmission Confidentiality/Integrity** | ◐ | App sets `Secure` cookies when `cookie_secure=True` and `SameSite=lax`. TLS itself is terminated by the reverse proxy/deployment (must be enabled in prod). |
| **SC-13 Cryptographic Protection** | ✅ | bcrypt for password storage; HMAC-SHA (HS256/384/512) for JWT signing via a validated secret. |
| **SC-23 Session Authenticity** | ✅ | Signed JWTs with expiry; `httponly` + `SameSite` cookies resist XSS/CSRF token theft. |
| **SC-28 Protection of Information at Rest** | ◐ | Passwords are bcrypt-hashed; **LLM provider API keys are AES-256-GCM encrypted at rest** (`app/llm/crypto.py`) — never stored or logged in plaintext, never in env/config. **MCP server connection credentials are encrypted at rest using this exact same mechanism** (`app/mcp/service.py` calls `app/llm/crypto.py`'s `encrypt`/`decrypt`/`mask` directly — a second, divergent encryption implementation was treated as a defect, not built) — never stored, logged, or included in an audit record's `details` in plaintext or ciphertext. A connection with no credential (an unauthenticated internal MCP server) has no ciphertext to protect and is a valid configuration. Full disk/column encryption for the rest of the schema is an operator/database control. |
| **SC-12 Key Management** | ◐ | The chassis refuses to boot in `env=prod` with a default/weak `JWT_SECRET` (FR-351, `app/config.py`); the LLM key-wrap secret `LLM_ENCRYPTION_KEY` fails closed at use time in prod if left at the in-code default (`app/llm/crypto.py`). MCP connection credentials reuse this same wrap key — there is no separate MCP encryption key to manage. Custody/rotation of `JWT_SECRET` + `LLM_ENCRYPTION_KEY` in a secrets vault is the operator's responsibility. |
| **SC-7 Boundary Protection** | ▢ | Network segmentation is an environmental control. |

---

## 6. System and Information Integrity (SI)

| Control | Status | Evidence / Notes |
|---|---|---|
| **SI-10 Information Input Validation** | ✅ | All request bodies validated by Pydantic v2 schemas; rejects unexpected fields (`extra="forbid"` on response models, typed inputs). File uploads are size-capped (`max_upload_bytes`) and stored under opaque UUID keys (no user-controlled path component → no traversal). |
| **SI-11 Error Handling** | ✅ | Production exception handler (`app/main.py`, `app/error_handlers.py`) strips stack traces from client responses in `env=prod` while always logging full detail internally. |
| **SI-12 Information Management & Retention** | ✅ | Retention is bounded and explicit (`audit_retention_days`); archival path documented (`app/db.py`, `app/audit/tasks.py`). |
| **SI-2 Flaw Remediation** / **SI-3 Malicious Code** / **SI-4 Monitoring** / **SI-7 Integrity** | ▢ | Patch management, anti-malware, runtime monitoring, and file-integrity verification are operational controls run in the deployment environment. Dependency versions are pinned in `pyproject.toml` to support reproducible, auditable builds. |

---

## 7. Known gaps and operator responsibilities

The chassis does **not** by itself make a system FISMA-Moderate compliant. Before an ATO,
the operator must address at least:

1. **MFA (IA-2(1), IA-2(2)).** Not in the chassis. Integrate at the IdP or as a slot for
   privileged accounts.
2. **TLS in production (SC-8).** Terminate HTTPS at the proxy and set `COOKIE_SECURE=true`.
3. **System-use banner text (AC-8).** Supply the organization-approved warning via
   `SYSTEM_USE_NOTIFICATION`.
4. **Audit review + forwarding (AU-6).** Schedule periodic review and forward `audit_logs`
   to a SIEM; schedule the AU-11 archival job.
5. **Secrets management (SC-12).** Supply a strong unique `JWT_SECRET` (the app refuses to
   boot in prod without one) and manage it in a secrets vault.
6. **Continuous monitoring (SI-2/3/4, CA-7), backup/recovery (CP), incident response (IR),
   configuration management (CM).** Organizational/operational controls outside the app.
7. **MCP server trust boundary (SC-7-adjacent, applies only if MCP client is used).** The
   chassis places no restriction on which URL an org admin may register as an MCP server
   connection — that admin is trusted the same way an org admin choosing an LLM provider key
   already is. An org admin who registers and enables a connection to a malicious or
   compromised MCP server gives that server's tools a channel into the org's LLM
   conversations; network egress allow-listing for outbound MCP connections, if desired, is a
   deployment-environment control (this package does not implement one). Every registration
   and enable/disable/delete mutation is audited (§3, AU-2/AU-3) so who registered or enabled
   a given connection is always attributable.

---

## 8. Change control for this document

This self-audit is maintained alongside the chassis. When a chassis change adds, removes, or
materially alters a security control, update the relevant row here in the **same change** and
note it in the chassis changelog. The control evidence (file paths, mechanisms) must stay
accurate to the shipped code.

_Last reviewed against chassis **v1.1.0** (this package, `python-fastapi-mt-fisma-moderate-llm`) for the MCP Client capability (§2 AC-3, §5 SC-28/SC-12, §7 item 7) added in that release. This document otherwise still carries reference-chassis v0.10.0 language inherited at fork time (e.g. §4's IA-2(1) row does not yet reflect this package's own real MFA implementation) — a pre-existing gap, not introduced by the MCP Client change, flagged here for a future full pass._
