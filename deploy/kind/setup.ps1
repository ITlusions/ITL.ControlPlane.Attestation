# Local kind cluster — Attestation Service
#
# Prerequisites: kind, kubectl, helm
#
# Usage:
#   .\deploy\kind\setup.ps1              # create cluster + install
#   .\deploy\kind\setup.ps1 -Destroy     # tear down everything

param(
    [switch]$Destroy
)

$ClusterName      = "attestation"
$Namespace        = "attestation"
$ReleaseName      = "attestation"
$ChartPath        = "$PSScriptRoot\..\helm\attestation"
$KindConfig       = "$PSScriptRoot\kind-config.yaml"
$TraefikValues    = "$PSScriptRoot\traefik-values.yaml"
$TraefikNamespace = "traefik"

function Write-Step { param($Msg) Write-Host "`n==> $Msg" -ForegroundColor Cyan }

# ── Destroy ──────────────────────────────────────────────────────────────────
if ($Destroy) {
    Write-Step "Deleting kind cluster '$ClusterName'..."
    kind delete cluster --name $ClusterName
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

# ── Create cluster ────────────────────────────────────────────────────────────
Write-Step "Creating kind cluster '$ClusterName'..."
kind create cluster --name $ClusterName --config $KindConfig
if ($LASTEXITCODE -ne 0) { Write-Error "kind create cluster failed"; exit 1 }

# ── Traefik ───────────────────────────────────────────────────────────────────
Write-Step "Adding Traefik Helm repo..."
helm repo add traefik https://traefik.github.io/charts 2>$null
helm repo update

Write-Step "Installing Traefik..."
helm upgrade --install traefik traefik/traefik `
    --namespace $TraefikNamespace --create-namespace `
    --values $TraefikValues `
    --wait --timeout 90s

Write-Step "Waiting for Traefik pod to be ready (up to 90s)..."
kubectl wait --namespace $TraefikNamespace `
    --for=condition=ready pod `
    --selector=app.kubernetes.io/name=traefik `
    --timeout=90s

# ── Namespace ─────────────────────────────────────────────────────────────────
Write-Step "Creating namespace '$Namespace'..."
kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f -

# ── Helm install ──────────────────────────────────────────────────────────────
Write-Step "Installing Helm release '$ReleaseName'..."
helm upgrade --install $ReleaseName $ChartPath `
    --namespace $Namespace `
    --set config.serviceUrl="http://attestation.local" `
    --wait --timeout 120s

# ── Status ────────────────────────────────────────────────────────────────────
Write-Step "Deployment status:"
kubectl get pods,svc,ingress -n $Namespace

Write-Host @"

Service is available at:
  http://attestation.local       (requires 'attestation.local -> 127.0.0.1' in hosts file)
  http://localhost:9508          (NodePort fallback — no hosts entry needed)

Add to hosts file (run as Administrator):
  Add-Content C:\Windows\System32\drivers\etc\hosts "127.0.0.1 attestation.local"
"@ -ForegroundColor Green
