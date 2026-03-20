# Setup & Installation (Helm)

## Preferred Method

Use the Helm chart in `helm/k8s-lite` for all deployments. This is the single source of truth for the Minimalist stack.

### Install
```sh
helm install minimalist ./helm/k8s-lite
```

### Upgrade
```sh
helm upgrade minimalist ./helm/k8s-lite
```

## Legacy/Manual

The `k8s-lite/` folder is deprecated and only for reference or manual/legacy use.
