#!/bin/bash
# Linkerd install script (Security Stamp)
curl -sL https://run.linkerd.io/install | sh
export PATH=$PATH:$HOME/.linkerd2/bin
linkerd check --pre
linkerd install | kubectl apply -f -
linkerd check
