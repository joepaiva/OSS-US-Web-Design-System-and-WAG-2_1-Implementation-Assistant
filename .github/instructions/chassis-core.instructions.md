---
applyTo: "app/**"
---
# Chassis core — do NOT modify
These are the vetted chassis files. Extend behavior only through the slots (`app/slots/**`). Never modify chassis core, bypass its auth/RBAC/audit primitives, or use forbidden patterns. Respect layer boundaries. If a task seems to require changing the core, STOP and flag it.
