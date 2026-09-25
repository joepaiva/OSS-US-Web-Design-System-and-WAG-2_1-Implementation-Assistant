# Accessibility Assistant — User Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
   - [Creating Your Account](#creating-your-account)
   - [Logging In](#logging-in)
   - [Navigating the Dashboard](#navigating-the-dashboard)
3. [Organizations & Workspaces](#organizations--workspaces)
   - [Switching Organizations](#switching-organizations)
   - [Understanding Your Role](#understanding-your-role)
4. [Submitting Content for Accessibility Review](#submitting-content-for-accessibility-review)
   - [Submitting a URL](#submitting-a-url)
   - [Submitting Raw HTML or Text](#submitting-raw-html-or-text)
   - [Submitting a Document](#submitting-a-document)
5. [Understanding Your Results](#understanding-your-results)
   - [The Results Summary](#the-results-summary)
   - [Severity Levels Explained](#severity-levels-explained)
   - [Issue Categories](#issue-categories)
   - [AI-Generated Remediation Guidance](#ai-generated-remediation-guidance)
6. [Working with Findings](#working-with-findings)
   - [Reviewing Individual Findings](#reviewing-individual-findings)
   - [Filtering and Sorting Findings](#filtering-and-sorting-findings)
   - [Marking Findings as Resolved](#marking-findings-as-resolved)
   - [Dismissing or Accepting Risk on a Finding](#dismissing-or-accepting-risk-on-a-finding)
7. [Remediation Suggestions](#remediation-suggestions)
   - [Reading AI-Generated Suggestions](#reading-ai-generated-suggestions)
   - [Applying Code Fixes](#applying-code-fixes)
   - [Requesting an Alternative Suggestion](#requesting-an-alternative-suggestion)
8. [Scan History](#scan-history)
   - [Browsing Past Scans](#browsing-past-scans)
   - [Comparing Scans](#comparing-scans)
   - [Re-running a Scan](#re-running-a-scan)
9. [Reports](#reports)
   - [Generating a Report](#generating-a-report)
   - [Report Formats](#report-formats)
   - [Sharing a Report](#sharing-a-report)
10. [Account & Profile Settings](#account--profile-settings)
    - [Updating Your Profile](#updating-your-profile)
    - [Changing Your Password](#changing-your-password)
    - [Setting Up Multi-Factor Authentication](#setting-up-multi-factor-authentication)
11. [Notifications & Preferences](#notifications--preferences)
12. [Accessibility of This Application](#accessibility-of-this-application)
13. [Troubleshooting](#troubleshooting)
14. [Glossary](#glossary)

---

## Introduction

The **Accessibility Assistant** is a web-based tool that helps teams identify, understand, and remediate accessibility barriers in digital content. It analyzes web pages, HTML fragments, and uploaded documents against established accessibility standards — primarily **WCAG 2.1** — and uses an AI assistant to explain each issue in plain language and suggest concrete fixes.

This guide is written for end users: content authors, developers, designers, and program managers who use the application day-to-day. You do not need a technical background to follow most workflows. Sections that involve reading or applying code are clearly marked.

> **Note on roles.** What you can see and do depends on the role your organization administrator has assigned to you. This guide covers all capabilities; features you cannot access will not appear in your navigation or will be shown as disabled.

---

## Getting Started

### Creating Your Account

1. Navigate to the application URL provided by your organization or system administrator.
2. Click **Create account** on the login page.
3. Enter your **email address** and choose a **password**.

   Password requirements:
   - At least **14 characters** long
   - Contains characters from at least **4 of the following classes:** uppercase letters, lowercase letters, numbers, and special characters (e.g., `!`, `@`, `#`, `$`)

4. Click **Register**.
5. Check your email inbox for a verification message and follow the link to confirm your address.
6. Once confirmed, log in with your new credentials.

> **Already have an invite?** If an administrator sent you an invitation link, click it directly. Your email address will be pre-filled and your organization membership will be established automatically after you set your password.

---

### Logging In

1. Go to the application login page.
2. Enter your **email address** and **password**.
3. Click **Sign in**.
4. If your account has **multi-factor authentication (MFA)** enabled, you will be prompted for your six-digit authenticator code. Enter it and click **Verify**.

**Forgot your password?**
Click **Forgot password?** on the login page, enter your email address, and follow the reset link sent to your inbox. Reset links expire after 30 minutes.

**Account locked?**
After three consecutive failed login attempts within a 15-minute window, your account is temporarily locked for 30 minutes. Wait for the lockout period to expire, then try again. Contact your administrator if you need immediate access restored.

---

### Navigating the Dashboard

After logging in you land on the **Dashboard**, which gives you a quick overview of recent activity within your current organization:

| Dashboard Element | What It Shows |
|---|---|
| **Recent Scans** | The five most recent accessibility scans, with status and date |
| **Open Findings** | Count of unresolved issues grouped by severity |
| **Trend Chart** | Issue counts over the past 30 days |
| **Quick Actions** | Buttons to start a new scan or generate a report |

The top navigation bar contains:
- **Logo / Home** — returns to the Dashboard
- **Scans** — browse and manage all scans
- **Reports** — generate and download reports
- **Organization name** (top-right) — switch organizations or access settings
- **Your name / avatar** (top-right) — access your profile and sign out

The left sidebar (on wider screens) provides the same primary navigation links plus any administrative options available to your role.

---

## Organizations & Workspaces

The Accessibility Assistant is multi-tenant. All scans, findings, and reports belong to an **organization** (also called a tenant or workspace). Your account may belong to more than one organization.

### Switching Organizations

1. Click your **organization name** in the top-right corner of any page.
2. A dropdown lists every organization you are a member of. Your current organization is checked.
3. Click the name of the organization you want to switch to.
4. The page reloads and all data shown now belongs to the selected organization.

> Your default organization is set in your profile. See [Account & Profile Settings](#account--profile-settings).

---

### Understanding Your Role

Your role within an organization determines what you can do:

| Role | Capabilities |
|---|---|
| **Admin** | Full access: manage members, configure organization settings, run scans, manage findings, generate reports, delete scans |
| **User** | Read access by default: view scans, view findings, view reports. Write capabilities (submit scans, manage findings) may be granted by an admin |

If you try to access a feature and see a **"You do not have permission"** message, contact your organization administrator to request the appropriate access.

---

## Submitting Content for Accessibility Review

A **scan** is the core unit of work in the Accessibility Assistant. You submit content, the system analyzes it, and findings are returned with AI-generated guidance.

To start a new scan, click **New Scan** from the Dashboard or the **Scans** page.

---

### Submitting a URL

Use this option to scan a live web page.

1. On the **New Scan** page, select the **URL** tab.
2. Enter the full URL of the page you want to scan (e.g., `https://www.example.gov/contact`).
3. *(Optional)* Enter a **Scan name** to make it easier to find later.
4. *(Optional)* Add **Tags** to categorize the scan (e.g., `homepage`, `forms`, `sprint-42`).
5. Click **Start Scan**.

The system fetches the page, renders it, and runs accessibility checks. Depending on page complexity, this typically takes **10–60 seconds**. You will see a progress indicator and be redirected to the results page automatically when the scan completes.

> **Authenticated pages:** If the page requires a login, the public URL scan cannot access it. Use the **HTML** submission method instead: log in manually, copy the rendered page source, and paste it as HTML.

---

### Submitting Raw HTML or Text

Use this option to scan a code snippet, a template, an email, or any HTML you have copied from your editor or browser.

1. On the **New Scan** page, select the **HTML** tab.
2. Paste your HTML or plain text into the text area.
3. *(Optional)* Enter a **Scan name**.
4. *(Optional)* Add **Tags**.
5. Click **Start Scan**.

The system parses the submitted markup and runs the same accessibility checks as a URL scan. Results are typically available within a few seconds for smaller snippets.

---

### Submitting a Document

Use this option to check a PDF, Word document, or other supported file format.

1. On the **New Scan** page, select the **Document** tab.
2. Click **Choose file** and select the file from your computer.

   Supported formats:
   - PDF (`.pdf`)
   - Microsoft Word (`.docx`)
   - Plain text (`.txt`)

3. *(Optional)* Enter a **Scan name**.
4. *(Optional)* Add **Tags**.
5. Click **Upload and Scan**.

The file is uploaded securely, converted to a reviewable format, and analyzed. Processing time depends on file size; most documents complete within 30 seconds.

---

## Understanding Your Results

When a scan completes, you are taken to the **Scan Results** page. This page is the central place to review everything the system found.

### The Results Summary

At the top of the results page you will see a **summary bar** with:

- **Total issues found** — the overall count of distinct accessibility findings
- **Breakdown by severity** — counts for Critical, Serious, Moderate, and Minor issues
- **WCAG criteria affected** — the number of distinct WCAG success criteria with at least one violation
- **Scan metadata** — the URL, file name, or label submitted; the date and time; and the scan duration

---

### Severity Levels Explained

Each finding is assigned a severity level based on the impact the barrier has on users with disabilities:

| Severity | Meaning | Examples |
|---|---|---|
| **Critical** | Completely blocks access for one or more disability groups | Missing form labels, images with no alternative text conveying essential information, keyboard traps |
| **Serious** | Significantly impairs access; workarounds are difficult or unavailable | Insufficient color contrast on body text, missing focus indicators, inaccessible error messages |
| **Moderate** | Creates friction or confusion; workarounds exist but are burdensome | Redundant link text, missing landmark regions, improper heading hierarchy |
| **Minor** | Best-practice deviation with limited real-world impact | Decorative images not hidden from assistive technology, verbose or redundant ARIA |

---

### Issue Categories

Findings are also grouped by **category** to help you understand the type of barrier:

- **Perceivable** — content cannot be perceived by some users (e.g., missing alt text, poor contrast)
- **Operable** — content cannot be operated by some users (e.g., keyboard inaccessibility, insufficient time limits)
- **Understandable** — content is confusing or unpredictable (e.g., unclear error messages, inconsistent navigation)
- **Robust** — content is not reliably interpreted by assistive technologies (e.g., invalid ARIA, malformed HTML)

These categories correspond to the four principles of WCAG (POUR).

---

### AI-Generated Remediation Guidance

For every finding, the AI assistant provides:

1. **Plain-language explanation** — what the issue is and why it matters to users with disabilities
2. **Affected users** — which disability groups are most impacted (e.g., blind users, keyboard-only users, users with cognitive disabilities)
3. **WCAG reference** — the specific success criterion violated, its level (A, AA, or AAA), and a link to the official guidance
4. **Suggested fix** — a concrete, actionable recommendation; for code issues, this includes a corrected code sample

The AI guidance is generated at the time of the scan and is specific to the content you submitted. It is not generic boilerplate.

> **Important:** AI-generated suggestions are provided as a starting point. Always review suggestions in the context of your specific content and consult your development team before applying changes to production systems.

---

## Working with Findings

### Reviewing Individual Findings

On the **Scan Results** page, each finding appears as a card or row in the findings list. Click any finding to open its **detail panel**, which shows:

- The full AI explanation and suggested fix
- The **source location** — the line number, element selector, or page region where the issue was found
- The **WCAG success criterion** with level and link
- The **current status** of the finding (Open, Resolved, Dismissed, Risk Accepted)
- The **history** of status changes and any notes added

---

### Filtering and Sorting Findings

Use the **filter bar** above the findings list to narrow results:

| Filter | Options |
|---|---|
| **Severity** | Critical, Serious, Moderate, Minor (multi-select) |
| **Status** | Open, Resolved, Dismissed, Risk Accepted |
| **Category** | Perceivable, Operable, Understandable, Robust |
| **WCAG Level** | A, AA, AAA |
| **Keyword** | Free-text search across finding titles and descriptions |

Use the **Sort** dropdown to order findings by:
- Severity (highest first — default)
- WCAG criterion
- Date found
- Status

Filters and sort order are preserved within your browser session.

---

### Marking Findings as Resolved

When you have fixed an issue in your content or code:

1. Open the finding detail panel.
2. Click **Mark as Resolved**.
3. *(Optional)* Enter a **note** describing what was changed and where (e.g., "Added `aria-label` to search button in `header.html`").
4. Click **Confirm**.

The finding status changes to **Resolved** and is moved out of the default open-findings view. Resolved findings remain in the scan record and are visible when you include resolved items in your filter.

> **Re-running a scan** after making fixes is the best way to confirm that resolved issues no longer appear. See [Re-running a Scan](#re-running-a-scan).

---

### Dismissing or Accepting Risk on a Finding

Sometimes a finding is not applicable to your context, or your organization has made a deliberate decision to accept the risk. Two additional statuses support this:

**Dismiss a finding** — use when the issue does not apply (e.g., the flagged element is not actually user-facing, or it is a false positive):

1. Open the finding detail panel.
2. Click **Dismiss**.
3. Enter a **required justification** explaining why the finding does not apply.
4. Click **Confirm**.

**Accept risk** — use when your organization acknowledges the issue but has decided not to remediate it at this time:

1. Open the finding detail panel.
2. Click **Accept Risk**.
3. Enter a **required justification** and, optionally, a **planned remediation date**.
4. Click **Confirm**.

Both actions are logged in the finding history and are visible in reports, supporting your organization's audit and compliance documentation.

---

## Remediation Suggestions

### Reading AI-Generated Suggestions

Each finding's detail panel contains a **Suggested Fix** section. This section is structured as:

1. **What to change** — a plain-language description of the specific change needed
2. **Where to change it** — the element, component, or template identified in the scan
3. **How to change it** — for technical issues, a code block showing the corrected markup, attribute, or style

Example (image missing alternative text):

```
What to change:
  Add descriptive alternative text to the <img> element.

Where to change it:
  <img src="/images/program-overview.jpg"> on line 42 of contact.html

How to change it:
  Before:
    <img src="/images/program-overview.jpg">

  After:
    <img src="/images/program-overview.jpg"
         alt="Program staff reviewing accessibility documentation at a conference table">
```

---

### Applying Code Fixes

Code suggestions are provided as **before/after diffs** or complete replacement snippets. To use them:

1. Copy the suggested code from the **How to change it** block using the **Copy** button (top-right of the code block).
2. Open the relevant file in your editor.
3. Locate the element using the line number or selector provided.
4. Replace the existing code with the suggested fix.
5. Test the change in your browser with a screen reader or keyboard-only navigation before committing.

> **Tip:** The line numbers and selectors in suggestions reflect the content as it was submitted. If your source file has changed since the scan, use the selector (e.g., `#main-nav > ul > li:first-child > a`) to locate the element rather than relying on the line number.

---

### Requesting an Alternative Suggestion

If the AI-generated suggestion does not fit your implementation (for example, your framework uses a different pattern for accessible labels), you can request an alternative:

1. In the finding detail panel, scroll to the **Suggested Fix** section.
2. Click **Request Alternative Suggestion**.
3. *(Optional)* In the text field that appears, describe your constraint or preferred approach (e.g., "We use React and manage labels through a `FormField` wrapper component").
4. Click **Generate Alternative**.

The AI assistant generates a new suggestion tailored to your context. Both the original and alternative suggestions are saved in the finding record.

> Alternative suggestion generation may take a few seconds. The original suggestion remains visible while the new one is being generated.

---

## Scan History

### Browsing Past Scans

Click **Scans** in the navigation to open the **Scan History** page. This page lists all scans run within your current organization, with:

- Scan name or URL/file submitted
- Date and time
- Submission type (URL, HTML, Document)
- Total findings and severity breakdown
- Current status (Completed, Processing, Failed)
- Tags

Use the **search bar** to find scans by name, URL, or tag. Use the **date range picker** to filter by when scans were run.

Click any scan row to open its results.

---

### Comparing Scans

To track progress over time, you can compare two scans of the same content:

1. On the **Scan History** page, select two scans using their checkboxes.
2. Click **Compare Selected**.
3. The **Comparison View** shows:
   - Issues present in both scans (persistent)
   - Issues in the older scan but not the newer (resolved)
   - Issues in the newer scan but not the older (new or regression)

This view is especially useful when preparing compliance reports or demonstrating remediation progress to stakeholders.

---

### Re-running a Scan

To re-scan the same URL or resubmit the same content after making fixes:

1. Open the original scan from **Scan History**.
2. Click **Re-run Scan** in the scan header.
3. For URL scans, the system fetches the current live page automatically.
4. For HTML or document scans, you are prompted to paste updated content or upload a new file.
5. Click **Start Scan**.

The new scan is saved as a separate record linked to the original, making it easy to compare results.

---

## Reports

### Generating a Report

Reports compile scan findings into a shareable document suitable for stakeholders, compliance officers, or development teams.

1. Navigate to **Reports** in the main navigation.
2. Click **New Report**.
3. Configure the report:

   | Field | Description |
   |---|---|
   | **Report name** | A descriptive title (e.g., "Q3 2026 Accessibility Audit — Public Website") |
   | **Scans to include** | Select one or more scans from your organization's history |
   | **Finding status filter** | Include Open, Resolved, Dismissed, Risk Accepted (any combination) |
   | **Severity filter** | Limit to specific severity levels if desired |
   | **Include AI suggestions** | Toggle whether remediation guidance appears in the report |
   | **Format** | PDF or CSV (see below) |

4. Click **Generate Report**.
5. Report generation runs in the background. You will receive an in-app notification when it is ready. For most reports this takes under 30 seconds.

---

### Report Formats

| Format | Best For |
|---|---|
| **PDF** | Executive summaries, compliance submissions, stakeholder presentations. Includes the summary bar, severity charts, and formatted finding details with AI suggestions. |
| **CSV** | Developer handoffs, issue tracking imports, data analysis. Contains one row per finding with all metadata fields. |

---

### Sharing a Report

Once a report is generated:

1. Open the report from the **Reports** page.
2. Click **Download** to save the file to your computer.
3. *(Admin only)* Click **Share Link** to generate a time-limited, read-only link you can send to people outside the application. Shared links expire after **7 days** by default; an admin can adjust this.

> Shared links do not require the recipient to have an account. They provide read-only access to that specific report only.

---

## Account & Profile Settings

Access your account settings by clicking your **name or avatar** in the top-right corner and selecting **Profile Settings**.

### Updating Your Profile

On the **Profile** tab you can update:

- **Display name**
- **Email address** (requires password confirmation; a verification email is sent to the new address)
- **Default organization** — the organization loaded automatically when you log in

Click **Save Changes** after making updates.

---

### Changing Your Password

1. Go to **Profile Settings** and select the **Security** tab.
2. Enter your **current password**.
3. Enter your **new password** (must meet the complexity requirements: 14+ characters, 4 character classes).
4. Confirm the new password.
5. Click **Update Password**.

You will remain logged in after a password change. All other active sessions are invalidated.

---

### Setting Up Multi-Factor Authentication

Multi-factor authentication (MFA) adds a second verification step at login using a time-based one-time password (TOTP) app such as **Google Authenticator**, **Authy**, or **1Password**.

**To enroll:**

1. Go to **Profile Settings → Security → Two-Factor Authentication**.
2. Click **Set Up MFA**.
3. Open your authenticator app and scan the QR code displayed, or manually enter the setup key shown below it.
4. Enter the **6-digit code** currently shown in your authenticator app to confirm the setup.
5. Click **Enable MFA**.
6. You are shown a set of **single-use backup codes**. **Save these immediately** in a secure location (password manager, printed copy in a safe). Each code can only be used once and allows you to log in if you lose access to your authenticator app.
7. Click **I have saved my backup codes** to complete enrollment.

**To use a backup code:**
On the MFA prompt at login, click **Use a backup code** and enter one of your saved codes.

**To disable MFA:**
Go to **Profile Settings → Security → Two-Factor Authentication** and click **Disable MFA**. You will be asked to confirm with your current authenticator code or a backup code.

> **Organization admins:** MFA is mandatory for accounts with platform-wide administrative privileges. If you hold that role, MFA cannot be disabled without first removing the administrative privilege.

---

## Notifications & Preferences

Access notification settings from **Profile Settings → Notifications**.

You can configure:

| Notification | Description | Default |
|---|---|---|
| **Scan completed** | Alert when a scan you submitted finishes processing | On |
| **Scan failed** | Alert when a scan encounters an error | On |
| **Report ready** | Alert when a report you requested is available for download | On |
| **New member joined** | *(Admins only)* Alert when a new user joins your organization | Off |

Notifications appear as **in-app alerts** (the bell icon in the top navigation bar). Email notifications are sent to your registered address if enabled in your organization's settings by an administrator.

---

## Accessibility of This Application

The Accessibility Assistant is built to meet **WCAG 2.1 Level AA** and is designed to be fully usable with:

- **Keyboard navigation** — all interactive elements are reachable and operable without a mouse
- **Screen readers** — the application uses semantic HTML, ARIA landmarks, and descriptive labels throughout
- **High-contrast mode** — the interface respects operating system high-contrast settings
- **Text resize** — the layout adapts to browser text size settings up to 200% without loss of content or functionality

The application uses the **U.S. Web Design System (USWDS)** component library, which is maintained to federal accessibility standards.

If you encounter an accessibility barrier within the application itself, please report it using the **Feedback** link in the footer, or contact your system administrator.

---

## Troubleshooting

### A scan is stuck on "Processing"

Scans typically complete within 60 seconds. If a scan shows **Processing** for more than 5 minutes:

1. Refresh the page — the status may have updated without the page refreshing automatically.
2. If still Processing, click **Cancel Scan** and try submitting again.
3. If the problem persists, contact your administrator. The scan ID (shown in the URL) helps with diagnosis.

---

### A URL scan returned no findings but I expected issues

Possible reasons:
- The page requires authentication. Use the **HTML** submission method with the authenticated page source.
- The page uses heavy JavaScript rendering. The scanner captures the initial HTML; dynamically injected content may not be fully analyzed. Submit the rendered HTML directly for more complete coverage.
- The page genuinely has no detectable automated violations. Note that automated scanning cannot catch all accessibility issues — manual testing with assistive technologies is always recommended alongside automated tools.

---

### The AI suggestion doesn't make sense for my content

AI suggestions are generated based on the submitted content and the detected issue. Occasionally a suggestion may be generic or not account for your specific framework or design system. Use **Request Alternative Suggestion** and describe your context to get a more tailored recommendation.

---

### I cannot see a scan or report that a colleague mentioned

Scans and reports are scoped to an organization. Confirm that you are viewing the correct organization (check the organization name in the top-right corner). If you are in the right organization and still cannot see the item, you may not have the required permission — contact your administrator.

---

### I am locked out of my account

Account lockout occurs after 3 failed login attempts within 15 minutes and lasts 30 minutes. Wait for the lockout to expire and try again with the correct password. If you have forgotten your password, use **Forgot password?** on the login page. If you need immediate access, contact your administrator.

---

### I lost my MFA device and do not have backup codes

Contact your organization administrator. An administrator can reset your MFA enrollment, which will allow you to log in with just your password and re-enroll a new device.

---

## Glossary

| Term | Definition |
|---|---|
| **Accessibility** | The practice of designing digital content so that people with disabilities can perceive, understand, navigate, and interact with it |
| **ARIA** | Accessible Rich Internet Applications — a set of HTML attributes that convey semantic information to assistive technologies |
| **Finding** | A single accessibility issue detected in a scan, with a severity, WCAG reference, location, and AI-generated guidance |
| **MFA / TOTP** | Multi-Factor Authentication using a Time-Based One-Time Password — a six-digit code generated by an authenticator app that changes every 30 seconds |
| **Organization** | A tenant workspace within the application; all scans, findings, and reports belong to an organization |
| **Remediation** | The process of fixing an accessibility issue in content or code |
| **Scan** | A single submission of content (URL, HTML, or document) for accessibility analysis |
| **Severity** | A rating (Critical, Serious, Moderate, Minor) indicating the impact of an accessibility barrier on users with disabilities |
| **WCAG** | Web Content Accessibility Guidelines — the internationally recognized standard for web accessibility, published by the W3C |
| **WCAG Level** | The conformance tier of a WCAG success criterion: Level A (minimum), Level AA (standard target for most organizations), Level AAA (enhanced) |