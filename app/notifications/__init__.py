"""In-app notifications (chassis v0.10).

Per-user notifications with a level + read state. Slots call
`app.notifications.service.notify(...)`; users read/clear them via the REST
API at `/api/notifications`.
"""
