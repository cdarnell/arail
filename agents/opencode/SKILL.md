# Opencode Agent Skill

Purpose:

Responsibilities:

Secrets: Opencode reads secrets from HashiCorp Vault (KV v2 or dynamic engines). Prefer CSI Secrets Store mounts or Vault Agent injection. Do not embed long-lived tokens in code; store user-provided tokens in Vault at `kv/data/opencode/user-tokens/` and display them obfuscated in UIs.

Integration Points:

Operational Commands:

Notes:
