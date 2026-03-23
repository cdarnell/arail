<#
Minimal script to mirror a list of public images into the local registry at localhost:5000.
Requires Docker or another container runtime with 'docker pull', 'docker tag', 'docker push'.

Usage: .\refresh-registry.ps1 -Images @('ghcr.io/owner/image:tag','docker.io/library/busybox:latest')
#>

param(
    [string[]]$Images = @(
        'ghcr.io/mastra/mastra-controlplane:latest',
        'ghcr.io/gentoofoo/model-prewarm:latest'
    )
)

foreach ($img in $Images) {
    # prefer regctl if available
    if (Get-Command regctl -ErrorAction SilentlyContinue) {
        Write-Host "Using regctl to copy $img -> localhost:5000"
        $localPath = $img -replace '^[^/]+/',''
        $dest = "localhost:5000/$localPath"
        & regctl image copy --insecure $img $dest
        if ($LASTEXITCODE -ne 0) { Write-Warning "regctl failed for $img"; continue }
        Write-Host "Mirrored: $img -> $dest"
    } else {
        Write-Host "regctl not found; falling back to docker for $img"
        Write-Host "Pulling $img"
        docker pull $img
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to pull $img"
            continue
        }

        # Strip registry host from name for local tagging (keep owner/repo:tag)
        $localPath = $img -replace '^[^/]+/',''
        $localImage = "localhost:5000/$localPath"

        Write-Host "Tagging $img -> $localImage"
        docker tag $img $localImage
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to tag $img -> $localImage"
            continue
        }

        Write-Host "Pushing $localImage"
        docker push $localImage
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to push $localImage"
            continue
        }

        Write-Host "Mirrored: $img -> $localImage"
    }
}

Write-Host "Done. Local registry available at http://localhost:5000"
