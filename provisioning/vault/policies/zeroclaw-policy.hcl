path "kv/data/zeroclaw/*" {
  capabilities = ["read", "list"]
}

path "sys/leases/revoke" {
  capabilities = ["update"]
}
