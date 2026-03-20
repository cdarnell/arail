terraform {
  required_providers {
    local = {
      source = "hashicorp/local"
      version = ">= 2.0.0"
    }
    null = {
      source = "hashicorp/null"
      version = ">= 3.0.0"
    }
  }
}

provider "local" {}
provider "null" {}

resource "null_resource" "install_k3s" {
  provisioner "local-exec" {
    command = <<EOT
      curl -sfL https://get.k3s.io | sh -
    EOT
  }
}

output "kubeconfig" {
  value = "~/.kube/config"
  description = "Kubeconfig path for the k3s cluster."
}
