"""BEE security layer (Phase 1).

Modules:
  netguard   — SSRF-hardened URL fetching for model-driven web tools
  secretscan — lightweight credential detection for repo/generated-file audits
  risk       — tool risk classification (levels, capabilities, approval, AST for Python)
  audit      — append-only, redacted audit trail for tool calls + guard decisions

Design rules:
  - fail closed: unknown = blocked / escalated, never silently allowed
  - never print or log secret VALUES (only masked forms)
  - pure-Python, no new runtime dependencies
"""
