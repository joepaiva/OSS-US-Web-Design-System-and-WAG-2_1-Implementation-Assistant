"""Embedded MCP (Model Context Protocol) client module (chassis v1.1.0).

Lets the chassis's embedded-LLM chat-completion call path discover and
invoke tools exposed by admin-registered external MCP servers -- client
role only; this chassis never exposes its own data/actions as an inbound
MCP server. FR-MCPCLIENT (specs/chassis-program/shared-capabilities/
MCP-CLIENT-REQUIREMENTS.md), DESIGN.md §6.14.

Every stored credential is AES-256-GCM encrypted at rest reusing
`app/llm/crypto.py` directly -- never a second encryption implementation
(Rule-7 parity, FR-MCPCLIENT-2).
"""
