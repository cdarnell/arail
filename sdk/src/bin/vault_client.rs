use anyhow::Result;
use reqwest::Client;
use serde_json::Value;

pub async fn read_kv_v2(client: &Client, vault_addr: &str, token: &str, path: &str) -> Result<Value> {
    // Vault KV v2 read: GET /v1/kv/data/<path>
    let url = format!("{}/v1/kv/data/{}", vault_addr.trim_end_matches('/'), path);
    let resp = client
        .get(&url)
        .bearer_auth(token)
        .send()
        .await?;
    let status = resp.status();
    let j = resp.json::<Value>().await?;
    if !status.is_success() {
        Err(anyhow::anyhow!("vault read error: {}", j))
    } else {
        // return the `data.data` object where the secret fields live
        let data = j.get("data").and_then(|d| d.get("data")).cloned().unwrap_or(Value::Null);
        Ok(data)
    }
}
