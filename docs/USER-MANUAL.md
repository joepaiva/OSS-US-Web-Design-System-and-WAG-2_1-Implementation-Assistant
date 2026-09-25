# User Manual

**Audience:** everyday users and administrators of this application.

This manual covers the features the chassis provides for everyone: creating an account,
signing in, managing your profile, and — for administrators — the admin shell. Features
specific to this particular application are documented separately by its authors.

---

## 1. Getting started

### Create an account

1. Open the application and choose **Get started** (or go to `/auth/register`).
2. Enter your email, full name, and a password.
3. Your password must be at least **14 characters** and include an **uppercase letter, a
   lowercase letter, a digit, and a special character**. The form tells you what's missing.
4. Submit. You are signed in automatically and taken to your dashboard.

### Sign in

1. Choose **Sign in** (or go to `/auth/login`).
2. Enter your email and password.
3. After too many failed attempts your account is temporarily locked for your protection.
   If you see a lockout message, wait the stated number of minutes and try again, or ask an
   administrator to help.

### Sign out

Use **Sign out** in the top navigation. This clears your session immediately.

---

## 2. Your account

Open **Account** (`/account`) to view your profile — your email, name, and the
organizations you belong to. Sign-out is also available here.

If your password is ever compromised, contact an administrator. Account lockout protects
against password guessing automatically; you do not need to do anything to enable it.

---

## 3. Organizations

Most data in the application belongs to an **organization**. You may belong to one or more.
Your default organization determines what you see by default. Administrators create
organizations and add members.

---

## 4. For administrators

If you hold an administrator role you'll see an **Admin** link in the top navigation. It
opens the admin shell at `/admin`.

### User Management (`/admin/users`)

- **Platform administrators** see and manage every user in the application.
- **Organization administrators** see and manage only the members of their organization.

You can:

- **Create a user** — enter their email, name, and password, and choose their role.
- **Deactivate a user** — they can no longer sign in. You cannot deactivate your own
  account.
- **Reactivate a user** — restores access.

Every one of these actions is recorded in the audit log with who did it and when.

### Organization Management (`/admin/orgs`)

*Platform administrators only.* List existing organizations and create new ones. Each
organization needs a name and a unique slug (a short URL-safe identifier).

### LLM Provider Keys (`/admin/llm`)

Manage the encrypted API keys the application uses to call large language models.

- **Organization administrators** add and deactivate their organization's own keys.
- **Platform administrators** additionally manage the shared key and choose which
  organizations may use it.

Keys are always shown masked (only the last few characters) and are stored encrypted — the
full value is never displayed after you save it.

### MCP Server Connections (`/admin/mcp`)

Register external MCP (Model Context Protocol) servers whose tools the embedded LLM may
discover and call mid-conversation — for example, an internal ticketing system or knowledge
base. This screen is available to organization administrators; there is no platform-shared
option (unlike LLM keys) because an MCP server is inherently a specific integration your
organization owns.

To register one:

1. Give it a **display name** (used to qualify its tools, e.g. `ticketing.create_issue`).
2. Enter the server's **URL**.
3. If the server requires authentication, enter its **credential** (a bearer token / API
   key). Leave it blank for an unauthenticated internal server — that's a fully supported
   configuration.
4. Click **Register server**.

A newly registered connection is **disabled** by default — registering it does not expose
its tools. Click **Enable** on the row once you're ready for the LLM to be able to discover
and call its tools. **Disable** or **Delete** it at any time; a disabled connection's tools
stop being offered on the very next request.

Credentials are always shown masked and stored encrypted, exactly like LLM provider keys
above — the full value is never displayed after you save it.

**Seeing it work:** the bundled Greeting Service demo (`/greet`) can call a registered MCP
server's tools. Register and enable a connection to an MCP server exposing a
regional-greeting-convention lookup tool, then submit a greeting request for a locale
outside the six built-in ones with "Use LLM translation" checked — the result's meta line
shows a "Tools used:" segment naming the tool the LLM actually called, visibly different from
the same request with no MCP connection enabled.

### System Health (`/admin/system-health`)

*Platform administrators only.* A live status board showing:

- the application version and the chassis version it was built on (known issue: the chassis-version field currently surfaces the app package version; CHASSIS_VERSION wiring is pending),
- the current environment (dev / test / prod),
- whether the **database** is reachable,
- whether **Redis** (background jobs) is reachable.

Use this page first whenever you're diagnosing a problem — it tells you immediately whether
a dependency is down.

### Reports (`/admin/reports`)

Usage figures at a glance: users, organizations (platform view), audit events and the most
frequent actions, stored files, notifications, and active LLM keys. Platform administrators
see platform-wide totals; organization administrators see their organization's figures.

### Documentation (`/admin/docs`)

Links to this manual, the **How It Works** overview, and the **Security Self-Audit**,
rendered inside the application so you don't have to leave the admin shell.

---

## 4b. Files and notifications (for everyone)

- **Files.** The application can store files for your organization. Anyone in your
  organization can upload, list, download, and delete its files; you never see another
  organization's files. Uploads are size-limited and integrity-checked.
- **Notifications.** The application can send you in-app notifications. You can list them,
  see an unread count, and mark them read individually or all at once. You only ever see
  your own notifications.

---

## 5. Accessibility

The interface is built on the U.S. Web Design System and targets **Section 508 / WCAG 2.1
AA**: full keyboard navigation, visible focus outlines, screen-reader-friendly labels, and
sufficient color contrast. A "Skip to main content" link is the first focusable element on
every page.

---

## 6. Getting help

If a page shows an error you don't understand, note the time and the `X-Request-ID` shown
in your browser's network tools, and give both to your administrator — that lets them find
the exact event in the logs.
