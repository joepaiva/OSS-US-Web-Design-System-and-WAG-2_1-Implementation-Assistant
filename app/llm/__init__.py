"""Embedded LLM module (chassis v0.9).

Rule-7 parity: provider API keys are stored AES-256-GCM encrypted in the
DB (per-org + platform-shared), resolved per request (org key → shared key
if policy allows → reject), and all completions route through a single
OpenAI-compatible endpoint (LiteLLM proxy by default).
"""
