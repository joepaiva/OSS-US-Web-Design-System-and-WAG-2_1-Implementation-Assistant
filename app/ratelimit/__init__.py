"""Request rate limiting (chassis v0.10).

A Redis-backed fixed-window per-client limiter, installed as ASGI
middleware. SC-5 (denial-of-service protection) at the application edge.
"""
