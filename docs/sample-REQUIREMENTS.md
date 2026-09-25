# REQUIREMENTS.md
## LeaveLite Test Application

## 1. Overview

LeaveLite Test Application is a small internal web application where employees submit leave requests and managers approve or deny requests for their direct reports.

The purpose of this project is not business completeness. The purpose is to provide a compact but realistic target for specification-driven code generation.


## 2. Product Goal

Generate a simple but non-trivial web application that demonstrates:
- login and session handling
- role-based authorization
- server-rendered HTML pages
- validated form submission
- explicit state transitions
- transactional audit and notification writes
- deterministic seed data
- automated tests guided by specification

## 3. Personas

### P1 — Employee
A standard user who can create, view, and cancel their own leave requests.


### P2 — Manager
A user who manages direct reports and can review, approve, and deny their pending requests. A Manager also has all Employee capabilities and can submit leave requests for themselves, which are routed to their own manager (or an administrator) for approval.




### P3 — Administrator
A privileged user who manages the system configuration, including creating and deactivating user accounts, assigning manager relationships, and configuring leave types and balances.



## 4. Scope

### In Scope
- local username/email + password authentication
- employee leave request creation
- employee request list and detail views
- employee cancel of pending requests
- manager pending queue (showing all pending requests assigned to that manager's direct reports)
- manager request detail and approve/deny actions (limited to requests within the manager's direct reports)



### Out of Scope
- leave balances
- accrual rules
- company holiday logic
- attachments
- calendar sync
- admin features
- multi-organization management UI
- third-party email delivery
- password reset flows — users who forget their password have no self-service recovery path in this version; this is a known limitation



## 5. Functional Requirements

### FR-01 Authentication
The system SHALL require authentication before access to any non-login page.

### FR-02 Roles
The system SHALL support exactly two roles in scope:
- `employee`
- `manager`

### FR-03 Employee Ownership
An employee SHALL be able to view only their own leave requests and notifications.

### FR-04 Manager Team Access
A manager SHALL be able to view only leave requests belonging to their direct reports.

### FR-05 Create Request
An employee SHALL be able to create a leave request with:
- `start_date`
- `end_date`
- `leave_type` in `Vacation | Sick | Other`
- optional `note` up to 500 characters

### FR-06 Date Validation
The system SHALL reject a request when:
- `start_date > end_date`
- request length exceeds 30 calendar days
- `Vacation` or `Other` starts before the user's current local date
- `Sick` starts more than 2 days in the past

For date comparison purposes, "current local date" SHALL be determined using the server's UTC date unless a timezone is stored on the user profile, in which case the user's stored timezone SHALL be used.


### FR-07 Overlap Prevention
The system SHALL reject creation of a request when the employee already has an overlapping request in status `Pending` or `Approved`. Two requests are considered overlapping when one request's `start_date` is less than or equal to the other's `end_date` AND the other's `start_date` is less than or equal to the first's `end_date` (inclusive boundary check). For example, a request ending on Day 5 and a new request starting on Day 5 ARE considered overlapping.


### FR-08 Request States
The system SHALL support exactly these statuses:
- `Pending`
- `Approved`
- `Denied`
- `Cancelled`

### FR-09 Allowed State Transitions
The system SHALL allow only these transitions, enforced by actor role:
- `Pending -> Approved` (manager only, for a direct report's request)
- `Pending -> Denied` (manager only, for a direct report's request)
- `Pending -> Cancelled` (employee only, for their own request)

A manager SHALL NOT be able to cancel a direct report's pending request; only the owning employee may cancel their own request.

All other transitions SHALL be rejected.


All other transitions SHALL be rejected.

### FR-10 Decision Actions
A manager SHALL be able to approve or deny a pending request for a direct report, with optional decision comment up to 500 characters. If a manager attempts to approve or deny a request for an employee who is not their direct report, the system SHALL return a 403 Forbidden response.


### FR-11 Audit Logging
The system SHALL create an immutable audit log row for every create, cancel, approve, and deny action that records:
- actor user id
- action type
- target type
- target id
- timestamp
- before snapshot
- after snapshot

Immutability SHALL be enforced at the application layer — no update or delete operations SHALL be exposed for audit log records. Database-level constraints (e.g., no UPDATE/DELETE grants) are recommended but not required for this test application.


### FR-12 Notifications
The system SHALL create in-app notifications for:
- manager when an employee creates a new pending request
- employee when a manager approves or denies a request

Each notification SHALL have a `read` boolean flag, defaulting to `false`. Users SHALL be able to mark individual notifications as read. The Notifications page SHALL visually distinguish unread from read notifications.


### FR-13 Transactional Side Effects
For create, cancel, approve, and deny operations, the request change, notifications, and audit log entries SHALL commit atomically in a single database transaction.

### FR-14 Employee Views
An employee SHALL have:
- My Requests page
- New Request page
- Request Detail page
- Notifications page

### FR-15 Manager Views
A manager SHALL have:
- Pending Queue page (showing all `Pending` requests for their direct reports)
- Team History page (showing all `Approved`, `Denied`, and `Cancelled` requests for their direct reports)
- Request Detail page
- Notifications page


### FR-16 Request Detail Rendering
The request detail page SHALL render available actions based on authenticated user role and current request state. Specifically:
- An employee viewing their own `Pending` request SHALL see a Cancel button.
- A manager viewing a direct report's `Pending` request SHALL see Approve and Deny buttons, each accompanied by an optional comment field (up to 500 characters).
- No action buttons SHALL appear for requests in terminal states (`Approved`, `Denied`, or `Cancelled`).


### FR-17 Session Timeout
The authenticated session SHALL expire after 60 minutes of inactivity by default, with the timeout value configurable via environment variable `SESSION_TIMEOUT_MINUTES`.


### FR-18 Password Storage
Passwords SHALL be hashed with bcrypt cost 12.

### FR-19 Login Rate Limiting
The login endpoint SHALL be rate limited to a maximum of 10 attempts per IP address per 15-minute window. Requests exceeding this limit SHALL receive a 429 Too Many Requests response.


### FR-20 Email Stub
An email notification stub MAY log intended email sends, but no real email integration is required.

## 6. Data Requirements

### DR-01 User
Fields:
- `id` UUID
- `name` VARCHAR(255) NOT NULL
- `email` VARCHAR(255) NOT NULL UNIQUE
- `password_hash` VARCHAR(255) NOT NULL
- `role` VARCHAR NOT NULL DEFAULT 'employee' — allowed values: 'employee', 'manager', 'admin'
- `manager_id` nullable FK to users.id
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now() — auto-populated on row creation
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now() — auto-updated on every row modification

**Indexes:**
- `users(email)` — unique index (implicit from UNIQUE constraint)
- `users(manager_id)` — supports lookups of direct reports






### DR-02 Leave Request
Fields:
- `id` UUID
- `employee_id` FK users.id
- `start_date` DATE NOT NULL
- `end_date` DATE NOT NULL — must be >= start_date
- `leave_type` VARCHAR NOT NULL — allowed values: 'vacation', 'sick', 'personal', 'unpaid'
- `note` TEXT nullable — employee-provided reason for the leave request
- `status` VARCHAR NOT NULL DEFAULT 'pending' — allowed values: 'pending', 'approved', 'rejected', 'cancelled'
- `decision_by_user_id` nullable FK users.id
- `decision_comment` nullable
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now() — auto-populated on row creation
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now() — auto-updated on every row modification

**Validation rule:** Requests where `end_date` is before `start_date` MUST be rejected with a validation error.

**Indexes:**
- `leave_requests(employee_id)` — supports fetching all requests for a given employee
- `leave_requests(status)` — supports filtering requests by approval status (e.g., pending queue for managers)
- `leave_requests(decision_by_user_id)` — supports lookups of decisions made by a specific manager





### DR-03 Notification
Fields:
- `id` UUID
- `user_id` FK users.id
- `kind` VARCHAR NOT NULL — allowed values: 'leave_submitted', 'leave_approved', 'leave_rejected', 'leave_cancelled'
- `payload_json` JSONB — expected keys: `{ "leave_request_id": UUID, "actor_name": string, "message": string }`
- `is_read` BOOLEAN NOT NULL DEFAULT false
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now() — auto-populated on row creation

**Indexes:**
- `notifications(user_id, is_read)` — supports fetching unread notifications for a given user





### DR-04 Audit Log
Fields:
- `id` UUID
- `actor_user_id` FK users.id
- `action_type` VARCHAR NOT NULL — allowed values: 'leave_created', 'leave_approved', 'leave_rejected', 'leave_cancelled', 'user_created', 'role_changed'
- `target_type` VARCHAR NOT NULL — allowed values: 'leave_request', 'user'
- `target_id` UUID NOT NULL
- `occurred_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- `before_json` JSONB nullable
- `after_json` JSONB nullable

**Indexes:**
- `audit_log(target_type, target_id)` — supports fetching the full audit history for any specific entity
- `audit_log(actor_user_id)` — supports fetching all actions performed by a given user


## 7. Logical Routes

### Authentication
- `GET /login`
- `POST /login`
- `POST /logout`

### Shared
- `GET /` — redirects to `/dashboard` if authenticated, or to `/login` if not
- `GET /notifications`
- `POST /notifications/:id/read`
- `POST /notifications/read-all`



### Employee
- `GET /dashboard` — employee dashboard displaying current leave balances and request history
- `GET /requests`
- `GET /requests/new`
- `POST /requests`
- `GET /requests/:id`
- `POST /requests/:id/cancel`


### Manager
- `GET /manager/queue`
- `GET /manager/requests/:id` — view request details with manager-scoped rendering (includes approve/deny actions)
- `POST /manager/requests/:id/approve`
- `POST /manager/requests/:id/deny` — accepts an optional `reason` field in the request body; if omitted, denial is recorded without a reason




## 8. Authorization Rules

### AR-01 Employee
Employee can:
- create own requests
- view own requests
- cancel own requests only when status is `Pending`
- view own notifications
- mark own notifications as read

Employee cannot:
- view other employees' requests
- approve or deny any request
- view another user's notifications
- delete notifications


Employee cannot:
- view other employees' requests
- approve or deny any request
- view another user's notifications


Employee cannot:
- view other employees’ requests
- approve or deny any request
- view another user’s notifications

### AR-02 Manager
Manager can:
- create own leave requests
- view own leave requests
- cancel own leave request only when status is `Pending`
- view requests for direct reports
- approve or deny direct-report requests only when status is `Pending`
- view own notifications
- mark own notifications as read

Manager cannot:
- create leave requests for others
- approve or deny requests outside their team
- view requests for unrelated employees
- approve their own leave requests
- cancel a direct report's leave request on their behalf
- delete notifications


> **Note (Manager's Own Leave Requests):** A Manager's own leave requests must be approved by their own Manager (i.e., the Manager to whom they report). If no Manager is assigned above them, their requests must be approved by an Admin. A Manager cannot approve their own requests under any circumstance.


Manager cannot:
- create leave requests for others
- approve or deny requests outside their team
- view requests for unrelated employees
- approve their own leave requests
- cancel a direct report's leave request on their behalf


> **Note (Manager's Own Leave Requests):** A Manager's own leave requests must be approved by their own Manager (i.e., the Manager to whom they report). If no Manager is assigned above them, their requests must be approved by an Admin. A Manager cannot approve their own requests under any circumstance.


Manager cannot:
- create leave requests for others
- approve or deny requests outside their team
- view requests for unrelated employees


Manager cannot:
- create leave requests for others
- approve or deny requests outside their team
- view requests for unrelated employees



### AR-03 Admin
Admin can:
- view all leave requests across all teams
- manage (create, edit, deactivate) user accounts
- view all notifications
- create own leave requests
- cancel own leave request only when status is `Pending`

Admin cannot:
- approve or deny leave requests on behalf of a Manager (unless explicitly granted)
- create leave requests for other users




> **Note (Role Change Mid-Flight):** If a user's role changes (e.g., a Manager is demoted to Employee), any pending approval requests previously assigned to them must be reassigned to their Manager or flagged for Admin review. The newly demoted user loses all Manager-level authorization immediately upon role change and must not be permitted to approve or deny any requests, including those already in their queue.


## 9. UX Requirements

### UX-01 Rendering Style
Pages SHALL be server-rendered HTML with basic responsive layout. Responsive layout SHALL support viewports down to 375px wide. A single-column stacked layout SHALL be used on mobile (viewports <768px); a sidebar or horizontal nav MAY be used on larger viewports (≥768px).


### UX-02 Navigation
Authenticated users SHALL see:
- role-appropriate navigation (defined below)
- current user name
- logout control
- notifications entry point

The notifications entry point SHALL be a nav link labeled "Notifications" with an unread count badge displayed inline when unread notifications exist (e.g., "Notifications (3)"). When there are no unread notifications, the badge SHALL NOT be displayed.

**Role-based navigation items:**

| Role     | Navigation Links                                                      |
|----------|-----------------------------------------------------------------------|
| Employee | Dashboard, My Requests, Notifications                                 |
| Manager  | Dashboard, My Requests, Team Requests, Notifications                  |
| Admin    | Dashboard, All Requests, Users, Notifications                         |

Nav links outside a user's role SHALL NOT be rendered in the HTML response.


**Role-based navigation items:**

| Role     | Navigation Links                                                      |
|----------|-----------------------------------------------------------------------|
| Employee | Dashboard, My Requests, Notifications                                 |
| Manager  | Dashboard, My Requests, Team Requests, Notifications                  |
| Admin    | Dashboard, All Requests, Users, Notifications                         |

Nav links outside a user's role SHALL NOT be rendered in the HTML response.


### UX-03 Forms
Create, cancel, approve, deny, login, notification-read, and edit/update actions SHALL use standard HTML forms with POST method. All state-mutating actions not explicitly listed above SHALL also use standard HTML forms with POST method.


### UX-04 Feedback
Validation failures and authorization failures SHALL produce visible user feedback without exposing internal details. Feedback SHALL be delivered as a flash message displayed at the top of the next rendered page. Field-level validation errors SHALL additionally appear inline adjacent to the offending field. Successful actions (form submission, approval, denial, cancellation) SHALL also produce visible confirmation feedback, delivered as a flash message on the subsequent page.



## 10. Non-Functional Requirements

### NFR-01 Stack Compliance
Implementation SHALL comply with the constitution's mandated stack (see `/CONSTITUTION.md` for the full technology list)


### NFR-02 Structured Logging
Application logs SHALL use structured key-value logging 

### NFR-03 Security
The system SHALL implement:
- CSRF protection for state-changing browser requests
- HTTP-only auth cookie: the auth cookie SHALL be named `session` (or a project-consistent name defined in config), set with `HttpOnly=true`, `SameSite=Lax`, and `Secure=true` in all non-development environments
- Session expiry SHALL be configured via environment variable (default: 24 hours); the value SHALL be documented in `.env.example`
- Server-side validation: all form inputs and API payloads SHALL be validated before processing; validation failures SHALL return HTTP 422 with field-level error messages rendered in the UI




### NFR-04 Docker Run
The project SHALL include a `docker-compose.yml` file that starts the application and a Postgres instance. Running `docker compose up` SHALL produce a fully functional local environment. Required environment variables SHALL be documented in a `.env.example` file.


### NFR-05 Testability
The codebase SHALL be organized so that:
- leave overlap detection logic (the business rule that prevents two approved leaves from covering the same date range for the same employee) is unit testable
- authorization logic is unit testable
- state transitions are unit testable



## 11. Acceptance Criteria

### AC-01 Overlap Rejection
For the purposes of this criterion, two date ranges **overlap** if and only if a new request's `start_date` ≤ an existing request's `end_date` AND the new request's `end_date` ≥ the existing request's `start_date`, where the existing request is in `Pending` or `Approved` status. Overlap is evaluated on calendar dates (inclusive bounds); partial-day or business-day distinctions are not applied.

Given an employee with an existing approved or pending request, when they submit an overlapping request, then the system rejects it with a validation error and no new row is created.


### AC-02 Team Isolation
Given a manager and a request outside their team, when the manager attempts to view it, then the system returns 404 (to avoid leaking existence of the request); when the manager attempts to approve or deny it, then the system returns 403 (the request exists but the manager is not authorized to act on it); and in all cases the system does not mutate data.


### AC-03 Invalid State Change
Given a request in `Approved`, `Denied`, or `Cancelled`, when an actor attempts an unsupported transition, then the system rejects the action and preserves original state.

### AC-04 Transactional Auditability
Given a successful create, cancel, approve, or deny action, then at least one matching audit log row exists for the mutation. A matching audit log row must contain at minimum: the actor's user ID, the action type (create/cancel/approve/deny), the affected request ID, and a UTC timestamp.


### AC-05 Transactional Notifications
Given a successful approve or deny action, then an unread employee notification exists in the same committed transaction as the state change. Given a successful cancel action on a pending request (whether initiated by the employee or a manager), then an unread notification exists for the affected employee in the same committed transaction as the state change.


### AC-06 Employee Cancel Rule
Given an employee’s own pending request, when they cancel it, then the request moves to `Cancelled` and an audit log row is written.

### AC-07 Password Storage
Given seeded or newly created users, passwords are stored as bcrypt hashes rather than plaintext, using a cost factor of ≥ 12.


### AC-08 Session Protection
Given an unauthenticated request, browser page navigations (requests expecting `text/html`) receive an HTTP 302 redirect to `/login`; API/JSON requests (requests expecting `application/json`) receive an HTTP 401 response with a JSON error body. In neither case is protected data returned.


## 12. Seed Data

The implementation SHALL include deterministic seed data:

### Users
- `M1` manager
- `E1` employee reporting to `M1`
- `E2` employee reporting to `M1`

> **Note (Admin Role):** If an admin role is defined in section 8 (Authorization Rules), seed data SHALL include at least one user with that role (e.g., `A1` admin, email: `admin@leavelite.test`, password: `password123`), and that user SHALL be added to the Login Credentials table below.

### Requests
- 3 sample requests for `E1` — 1 with status `APPROVED`, 1 with status `REJECTED`, and 1 with status `CANCELLED` (or `APPROVED`); all sample requests for `E1` SHALL have end dates in the past (e.g., within the prior calendar year)




### Login Credentials
Seed credentials MUST be stored hashed in the database. The following credentials SHALL be used:

| User | Email | Password (plaintext for seeding) |
|------|-------|----------------------------------|
| `M1` | `manager@leavelite.test` | `password123` |
| `E1` | `employee1@leavelite.test` | `password123` |
| `E2` | `employee2@leavelite.test` | `password123` |




## 13. Assumptions

- Single organization / tenant for the demo environment. No multi-tenancy isolation is required. A single organization record will be seeded (see Section 12). All data belongs to this organization implicitly; no org-scoping logic is needed in queries.
- All dates are stored and compared as date-only values (no time component). The server timezone is assumed to be UTC. No timezone conversion is performed. The client submits dates as YYYY-MM-DD strings and the server stores them as-is.
- Email delivery is simulated by logging the email recipient, subject, and body to the server console (stdout). No real SMTP integration or third-party email service is required.

