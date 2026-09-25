"""Slots — where LLM-generated business logic lives.

Chassis-owned code is everything OUTSIDE `app/slots/`. LLMs only create new
packages here (e.g. `app/slots/inventory/`, `app/slots/billing/`).

ARCHITECTURE.md §3 spells out the canonical slot skeleton.

`app/slots/example/` is the reference implementation — every slot LLMs
create MUST mirror its shape.
"""
