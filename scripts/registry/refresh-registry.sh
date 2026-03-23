#!/usr/bin/env bash
# Mirror a list of images into the local registry (localhost:5000)
# Usage: ./refresh-registry.sh images.txt

set -euo pipefail

IMAGES_FILE=${1:-}
if [ -z "$IMAGES_FILE" ]; then
  echo "Usage: $0 <images-file>"
  echo "Images file should contain one image reference per line, e.g. ghcr.io/owner/image:tag";
  exit 2
fi

while IFS= read -r img || [ -n "$img" ]; do
  img=$(echo "$img" | xargs)
  [ -z "$img" ] && continue
  # prefer regctl if available for registry copy operations
  if command -v regctl >/dev/null 2>&1; then
    echo "Using regctl to copy $img -> localhost:5000"
    # regctl copy supports source and destination; use --insecure to allow self-signed local certs if needed
    regctl image copy --insecure "${img}" "localhost:5000/$(echo "$img" | sed -E 's|^[^/]+/||')" || { echo "regctl failed for $img"; continue; }
  else
    echo "regctl not found; falling back to docker for $img"
    echo "Pulling $img"
    docker pull "$img" || { echo "Failed to pull $img"; continue; }

    # Strip registry host from name for local tagging
    localPath=$(echo "$img" | sed -E 's|^[^/]+/||')
    localImage="localhost:5000/$localPath"

    echo "Tagging $img -> $localImage"
    docker tag "$img" "$localImage" || { echo "Failed to tag $img"; continue; }

    echo "Pushing $localImage"
    docker push "$localImage" || { echo "Failed to push $localImage"; continue; }
  fi

  echo "Mirrored: $img -> $localImage"
done < "$IMAGES_FILE"

echo "Done. Local registry available at http://localhost:5000"
