use anyhow::Result;
use clap::Parser;
use reqwest::Client;
use serde::Deserialize;
use std::process::Command;
use std::time::Duration;
use std::sync::Arc;

use prometheus::{Encoder, IntCounterVec, Opts, Registry, TextEncoder};
use hyper::{Body, Request, Response, Server, Method, StatusCode};
use hyper::service::{make_service_fn, service_fn};
use tracing::{info, warn, error};
use tracing_appender::rolling;
use tracing_subscriber::fmt::Layer;
use tracing_subscriber::prelude::*;
mod vault_client;

#[derive(Parser)]
struct Args {
    /// Name or id of the agent to check
    #[arg(short, long)]
    agent: String,

    /// Health endpoint to probe (default: http://localhost:9000/healthz)
    #[arg(short, long, default_value = "http://localhost:9000/healthz")]
    health: String,

    /// Restart command to run when attempting a restart (shell string)
    #[arg(short, long, default_value = "systemctl restart agent.service")]
    restart_cmd: String,

    /// Small distilled sysadmin LLM endpoint (100M) - POST {"prompt":..}
    #[arg(long, default_value = "http://localhost:8001/solve")]
    small_llm: String,

    /// Medium LLM endpoint used as intermediate escalation (e.g., 350M)
    #[arg(long, default_value = "http://localhost:8002/solve")]
    medium_llm: String,

    /// Large model endpoint used for final escalation
    #[arg(long, default_value = "http://localhost:8080/generate")]
    large_llm: String,

    /// If set, apply commands suggested by LLMs automatically (dangerous!)
    #[arg(long)]
    auto_apply: bool,

    /// When set, be extra-safe and skip potentially destructive commands
    #[arg(long)]
    safe_mode: bool,

    /// Which manager is invoking this (e.g., zeroclaw, opencode)
    #[arg(long, default_value = "zeroclaw")]
    managed_by: String,
    /// Vault address (e.g., https://vault.vault.svc.cluster.local:8200)
    #[arg(long, default_value = "")]
    vault_addr: String,
    /// Vault token (if empty, will try VAULT_TOKEN env var)
    #[arg(long, default_value = "")]
    vault_token: String,
    /// KV v2 path to load secrets from (e.g., opencode/db)
    #[arg(long, default_value = "")]
    vault_kv: String,
    /// Kubernetes role name configured in Vault for the pod service account
    #[arg(long, default_value = "")]
    vault_k8s_role: String,
    /// Path to the Kubernetes service account JWT (defaults to in-cluster path)
    #[arg(long, default_value = "/var/run/secrets/kubernetes.io/serviceaccount/token")]
    vault_sa_jwt_path: String,
}

#[derive(Deserialize)]
struct LlmResponse {
    response: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging: file + stdout
    let file_appender = rolling::daily("./logs", "agent_escalator.log");
    let (non_blocking, _guard) = tracing_appender::non_blocking(file_appender);
    let file_layer = Layer::default().with_writer(non_blocking);
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::from_default_env())
        .with(tracing_subscriber::fmt::layer())
        .with(file_layer)
        .init();

    let args = Args::parse();
    let client = Client::new();

    // If Vault settings present, attempt to read KV v2 secrets and log obfuscated keys
    if !args.vault_addr.is_empty() && !args.vault_kv.is_empty() {
        // Determine a Vault token: CLI arg -> env VAULT_TOKEN -> Kubernetes-auth exchange
        let mut token = String::new();
        if !args.vault_token.is_empty() {
            token = args.vault_token.clone();
        } else if let Ok(envt) = std::env::var("VAULT_TOKEN") {
            if !envt.is_empty() { token = envt; }
        }

        // If vault_k8s_role not provided, try to auto-derive from in-cluster namespace
        if args.vault_k8s_role.is_empty() {
            if let Ok(ns) = read_kubernetes_namespace(&args.vault_sa_jwt_path) {
                // derive a default role name from namespace
                // e.g., namespace `opencode` -> `opencode-role`
                warn!(namespace=%ns, "No --vault-k8s-role provided; deriving role from namespace");
                // SAFETY: mutate args? we can't mutate args (it is borrowed), so set local_role
            }
        }

        // Determine role to use for k8s login (priority: CLI arg -> derived from namespace -> empty)
        let mut derived_role = args.vault_k8s_role.clone();
        let mut used_namespace_fallback = false;
        if derived_role.is_empty() {
            // Prefer pod labels (app) when available, else fall back to namespace
            if let Ok((maybe_pod, maybe_ns, labels)) = read_pod_info() {
                if let Some(app) = labels.get("app") {
                    if let Some(ns) = maybe_ns {
                        derived_role = format!("{}-{}-role", ns, app);
                    } else {
                        derived_role = format!("{}-role", app);
                    }
                } else if let Some(ns) = maybe_ns {
                    derived_role = format!("{}-role", ns);
                    used_namespace_fallback = true;
                }
                if let Some(pn) = maybe_pod {
                    info!(pod=%pn, "Discovered pod name from downward API");
                }
            } else if let Ok(ns) = read_kubernetes_namespace(&args.vault_sa_jwt_path) {
                derived_role = format!("{}-role", ns);
                used_namespace_fallback = true;
            }
        }

        // Log a high-visibility warning if we had to fall back to namespace-level role
        if used_namespace_fallback && args.vault_k8s_role.is_empty() {
            warn!(derived_role=%derived_role, "Falling back to namespace-derived Vault role; consider setting an 'app' label or explicit --vault-k8s-role for least-privilege access");
        }

        if token.is_empty() && !derived_role.is_empty() {
            // Try Kubernetes ServiceAccount JWT exchange
            match std::fs::read_to_string(&args.vault_sa_jwt_path) {
                Ok(jwt) => {
                    match vault_kubernetes_login(&client, &args.vault_addr, &derived_role, &jwt).await {
                        Ok(t) => { token = t; info!("Obtained Vault token via Kubernetes auth"); }
                        Err(e) => { warn!(%e, "Kubernetes auth login to Vault failed"); }
                    }
                }
                Err(e) => {
                    warn!(%e, "Failed to read service account JWT from path");
                }
            }
        }

        if token.is_empty() {
            warn!("Vault address provided but no token available; skipping Vault fetch");
        } else {
            match vault_client::read_kv_v2(&client, &args.vault_addr, &token, &args.vault_kv).await {
                Ok(data) => {
                    if let Some(map) = data.as_object() {
                        for (k, v) in map {
                            let s = v.as_str().unwrap_or("<binary>");
                            let masked = if s.len() > 4 { format!("****{}", &s[s.len()-4..]) } else { "****".to_string() };
                            info!(key=%k, masked_value=%masked, "Loaded secret from Vault");
                        }
                    }
                }
                Err(e) => {
                    warn!(%e, "Failed to read secrets from Vault");
                }
            }
        }
    }

async fn vault_kubernetes_login(client: &Client, vault_addr: &str, role: &str, jwt: &str) -> Result<String> {
    let url = format!("{}/v1/auth/kubernetes/login", vault_addr.trim_end_matches('/'));
    let payload = serde_json::json!({"role": role, "jwt": jwt});
    let r = client.post(&url).json(&payload).send().await?;
    let j: serde_json::Value = r.json().await?;
    if !r.status().is_success() {
        return Err(anyhow::anyhow!("vault k8s login failed: {}", j));
    }
    let token = j.get("auth").and_then(|a| a.get("client_token")).and_then(|t| t.as_str()).ok_or_else(|| anyhow::anyhow!("no client_token in response"))?;
    Ok(token.to_string())
}

fn read_kubernetes_namespace(sa_jwt_path: &str) -> Result<String> {
    // Namespace file path is in same dir as token by default
    let ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace";
    match std::fs::read_to_string(ns_path) {
        Ok(s) => Ok(s.trim().to_string()),
        Err(e) => Err(anyhow::anyhow!("failed to read k8s namespace: {}", e)),
    }
}

fn read_pod_info() -> Result<(Option<String>, Option<String>, std::collections::HashMap<String,String>)> {
    // Try env vars first
    let pod_name = std::env::var("POD_NAME").ok();
    let pod_namespace = std::env::var("POD_NAMESPACE").ok();

    // Common downward API path for labels
    let labels_path = "/etc/podinfo/labels";
    let mut labels = std::collections::HashMap::new();
    if let Ok(content) = std::fs::read_to_string(labels_path) {
        for line in content.lines() {
            let l = line.trim();
            if l.is_empty() { continue; }
            // support formats: key=value  key: value  key="value"
            if let Some(pos) = l.find('=') {
                let k = l[..pos].trim().to_string();
                let mut v = l[pos+1..].trim().to_string();
                if v.starts_with('"') && v.ends_with('"') && v.len()>=2 {
                    v = v[1..v.len()-1].to_string();
                }
                labels.insert(k, v);
                continue;
            }
            if let Some(pos) = l.find(":") {
                let k = l[..pos].trim().to_string();
                let v = l[pos+1..].trim().trim_matches('"').to_string();
                labels.insert(k, v);
                continue;
            }
            // fallback: parse space-separated key value
            let parts: Vec<&str> = l.split_whitespace().collect();
            if parts.len() >= 2 {
                labels.insert(parts[0].to_string(), parts[1].to_string());
            }
        }
    }

    Ok((pod_name, pod_namespace, labels))
}

    println!("Checking health of agent '{}' at {}", args.agent, args.health);

    if check_health(&client, &args.health).await {
        println!("Agent is healthy — nothing to do.");
        return Ok(());
    }

    println!("Agent unhealthy — attempting fast restart using configured restart command.");
    if let Err(e) = run_restart(&args.restart_cmd) {
        eprintln!("Restart command failed to start: {}", e);
    } else {
        tokio::time::sleep(Duration::from_secs(5)).await;
        if check_health(&client, &args.health).await {
            println!("Restart succeeded — agent healthy.");
            return Ok(());
        }
    }

    // Metrics: (create a minimal registry if not already added)
    let registry = Registry::new();
    let manager_invocations = IntCounterVec::new(Opts::new("managed_invocations_total", "Invocations by manager"), &["manager"]).unwrap();
    registry.register(Box::new(manager_invocations.clone())).ok();

    // record which manager invoked this
    manager_invocations.with_label_values(&[&args.managed_by]).inc();

    // Define escalation tiers (in increasing power/cost)
    let tiers = vec![
        ("small", args.small_llm.clone(), 1u8),
        ("medium", args.medium_llm.clone(), 1u8),
        ("large", args.large_llm.clone(), 1u8),
    ];

    for (level_idx, (level_name, endpoint, attempts)) in tiers.iter().enumerate() {
        println!("Escalation level {}: {} -> {}", level_idx + 1, level_name, endpoint);
        for attempt in 1..=*attempts {
            println!("Attempt {}/{} at level {}", attempt, attempts, level_name);
            let prompt = format!(
                "Agent '{}' at {} failed health check and restart. Provide safe, minimal shell steps to diagnose and recover. Return plain commands or 'none' if nothing helps. Indicate confidence and risk.",
                args.agent, args.health
            );

            match call_llm(&client, endpoint, &prompt).await {
                Ok(resp) => {
                    println!("{} LLM suggestion:\n{}", level_name, resp.response);
                    if args.auto_apply {
                        // execute suggested commands with safe-mode checks
                        if let Err(e) = execute_suggested_with_policy(&resp.response, args.safe_mode) {
                            eprintln!("Execution error: {}", e);
                        }
                        tokio::time::sleep(Duration::from_secs(5)).await;
                        if check_health(&client, &args.health).await {
                            println!("Recovered after {}-LLM remediation.", level_name);
                            return Ok(());
                        }
                    }
                }
                Err(e) => {
                    eprintln!("{} LLM call error: {} — moving to next level.", level_name, e);
                }
            }
        }
        println!("Level {} did not recover the agent; escalating to next level.", level_name);
    }

    eprintln!("All escalation tiers attempted — manual intervention required.");
    Ok(())
}

async fn check_health(client: &Client, url: &str) -> bool {
    match client.get(url).timeout(Duration::from_secs(3)).send().await {
        Ok(r) => r.status().is_success(),
        Err(_) => false,
    }
}

fn run_restart(cmd: &str) -> Result<()> {
    println!("Running restart command: {}", cmd);
    if cfg!(windows) {
        let status = Command::new("powershell").args(["-Command", cmd]).status()?;
        if status.success() { Ok(()) } else { Err(anyhow::anyhow!("restart command failed")) }
    } else {
        let status = Command::new("sh").arg("-c").arg(cmd).status()?;
        if status.success() { Ok(()) } else { Err(anyhow::anyhow!("restart command failed")) }
    }
}

async fn call_llm(client: &Client, endpoint: &str, prompt: &str) -> Result<LlmResponse> {
    let payload = serde_json::json!({"prompt": prompt});
    let r = client
        .post(endpoint)
        .json(&payload)
        .timeout(Duration::from_secs(10))
        .send()
        .await?;
    let lr = r.json::<LlmResponse>().await?;
    Ok(lr)
}

fn execute_suggested_with_policy(body: &str, safe_mode: bool) -> Result<()> {
    // Very simple parser: execute lines that look like shell commands (naive)
    // safe_mode prevents execution of destructive commands
    let blacklist = ["rm -rf", "shutdown", "reboot", "poweroff", ":(){ :|:& };:"]; // include fork bomb pattern
    for line in body.lines() {
        let l = line.trim();
        if l.is_empty() { continue; }
        // skip lines that look like explanations
        if l.ends_with(":") || l.starts_with("#") || l.starts_with("- ") { continue; }

        // simple blacklist check
        if safe_mode {
            for b in &blacklist {
                if l.contains(b) {
                    eprintln!("Skipping potentially destructive command in safe mode: {}", l);
                    continue;
                }
            }
        }

        println!("Executing suggested command: {}", l);
        // execute
        if cfg!(windows) {
            let status = Command::new("powershell").args(["-Command", l]).status()?;
            if !status.success() { eprintln!("Command failed: {}", l); }
        } else {
            let status = Command::new("sh").arg("-c").arg(l).status()?;
            if !status.success() { eprintln!("Command failed: {}", l); }
        }
    }
    Ok(())
}

async fn start_metrics_server(registry: Arc<Registry>) {
    let make_svc = make_service_fn(move |_| {
        let registry = registry.clone();
        async move {
            Ok::<_, hyper::Error>(service_fn(move |req: Request<Body>| {
                let registry = registry.clone();
                async move {
                    if req.method() == Method::GET && req.uri().path() == "/metrics" {
                        let encoder = TextEncoder::new();
                        let metric_families = registry.gather();
                        let mut buffer = Vec::new();
                        encoder.encode(&metric_families, &mut buffer).unwrap();
                        Ok::<_, hyper::Error>(Response::new(Body::from(buffer)))
                    } else {
                        let mut not_found = Response::default();
                        *not_found.status_mut() = StatusCode::NOT_FOUND;
                        Ok::<_, hyper::Error>(not_found)
                    }
                }
            }))
        }
    });

    let addr = ([127,0,0,1], 9898).into();
    let server = Server::bind(&addr).serve(make_svc);
    info!(addr=%addr, "Metrics server running");
    if let Err(e) = server.await {
        error!(%e, "Metrics server error");
    }
}
