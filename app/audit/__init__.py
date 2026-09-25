"""Audit log subsystem.

Two pieces:
  - models.AuditLog — append-only table; chassis never deletes rows.
  - decorator.audited(action, entity_type) — wraps async service functions,
    writing an audit row on successful return. Failures do NOT write
    (chassis would have already logged the exception elsewhere).
"""
