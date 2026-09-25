"""Embedded file storage (chassis v0.10).

Org-scoped file upload/download backed by local disk, with metadata in the
`file_objects` table. Slots call `app.files.service` directly, or expose the
REST API mounted at `/api/files`.
"""
