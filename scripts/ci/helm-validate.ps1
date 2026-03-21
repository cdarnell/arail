Param()
Write-Output "Running helm dependency build for helm/minimalist..."
try {
  helm dependency build "${PSScriptRoot}\..\..\helm\minimalist" | Write-Output
} catch {
  Write-Warning "helm dependency build failed or helm not installed; continuing to validator"
}

Write-Output "Running helm-template validator"
bash "${PSScriptRoot}/../validate-helm-vault.sh"

Write-Output "CI helm validation completed"
