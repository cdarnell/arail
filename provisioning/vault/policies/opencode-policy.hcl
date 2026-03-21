path "kv/data/opencode/*" {
  capabilities = ["read", "list"]
}

path "database/creds/opencode-role" {
  capabilities = ["read"]
}
