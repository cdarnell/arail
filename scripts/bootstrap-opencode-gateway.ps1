param(
  [string] $Registry = "docker.io/gentoofoo",
  [string] $ImageTag = $(Get-Date -Format "yyyyMMddHHmmss"),
  [string] $HelmRelease = "minimalist",
  [string] $Namespace = "default",
  [string] $ValuesFile = "helm/minimalist/values.yaml",
  [string] $VaultTokenFile = "",
  [string] $LMStudioWebhookSecretFile = "",
  [string] $WebhookBaseUrl = "",
  [string] $LMStudioUrl = "",
  [switch] $DryRun
)

Set-StrictMode -Version Latest

function Check-Command($cmd) {
  $which = Get-Command $cmd -ErrorAction SilentlyContinue
  if (-not $which) { Write-Error "$cmd is not installed or not in PATH"; exit 2 }
}

Check-Command docker
Check-Command helm

$ImageName = "opencode-gateway"
$Image = "$Registry/$ImageName:$ImageTag"

Write-Host "Building image $Image..."
if ($DryRun) { Write-Host "DRY RUN: docker build -t $Image ./opencode-gateway" } else {
  docker build -t $Image ./opencode-gateway
}

Write-Host "Pushing image $Image..."
if ($DryRun) { Write-Host "DRY RUN: docker push $Image" } else {
  docker push $Image
}

# Build --set arguments
$setList = @()
$setList += "opencodeGateway.image.repository=$Registry/$ImageName"
$setList += "opencodeGateway.image.tag=$ImageTag"
if ($WebhookBaseUrl) { $setList += "opencodeGateway.env.WEBHOOK_BASE_URL=$WebhookBaseUrl" }
if ($LMStudioUrl) { $setList += "opencodeGateway.env.LM_STUDIO_URL=$LMStudioUrl" }

$setArg = $setList -join ','

# Build --set-file args for secrets (Helm will read file content)
$setFileArgs = @()
if ($VaultTokenFile -and (Test-Path $VaultTokenFile)) { $setFileArgs += "--set-file opencodeGateway.secrets.vaultToken=$VaultTokenFile" }
if ($LMStudioWebhookSecretFile -and (Test-Path $LMStudioWebhookSecretFile)) { $setFileArgs += "--set-file opencodeGateway.secrets.lmStudioWebhookSecret=$LMStudioWebhookSecretFile" }

$helmCmd = "helm upgrade --install $HelmRelease helm/minimalist -n $Namespace --create-namespace -f $ValuesFile"
if ($setArg) { $helmCmd = "$helmCmd --set $setArg" }
if ($setFileArgs.Count -gt 0) { $helmCmd = "$helmCmd $($setFileArgs -join ' ')" }

Write-Host "Running Helm upgrade:"
Write-Host $helmCmd
if ($DryRun) { Write-Host "DRY RUN: Skipping helm upgrade" } else {
  iex $helmCmd
}

Write-Host "Bootstrap complete. Image: $Image. Helm release: $HelmRelease in namespace $Namespace"
