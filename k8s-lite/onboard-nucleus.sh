#!/bin/bash
echo "Welcome to the Nucleus Academy Onboarding."
echo "------------------------------------------"

# 1. Check Linkerd Health
echo "Checking Schoolhouse Security (Linkerd)..."
linkerd check || echo "Warning: Linkerd not found. Running in insecure mode."

# 2. Verify GPU for the OMEN-i9-3090
echo "Checking GPU Availability..."
kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu

# 3. Initializing the Janitor (ZeroClaw)
echo "Engaging ZeroClaw SRE..."
zeroclaw onboard --api-key $1 --provider openrouter

# 4. Setting the Major
echo "What is your focus for this lab session? (NLP/Vision/SRE)"
read focus
echo "Teacher Agent (OpenCode.ai) is now tailoring your curriculum for $focus..."

echo "------------------------------------------"
echo "Onboarding Complete. Your Rust Workshop is ready at: http://lab.local/terminal"
