#!/bin/bash
# deploy.sh - Automatisiertes Deployment-Skript für Ninko
# 
# Dieses Skript baut das Docker-Image, pusht es zu Docker Hub
# und deployt es auf den Kubernetes-Cluster.
# 
# Voraussetzungen:
# - Docker und docker-compose installiert
# - kubectl konfiguriert mit Zugriff auf den Cluster
# - Docker Hub Login (docker login)
# 
# Verwendung:
# ./deploy.sh [--skip-push] [--local-only]
# 
# Optionen:
#   --skip-push    Überspringt das Pushen zu Docker Hub
#   --local-only   Führt nur lokalen Docker Compose Deployment durch

set -e

# Farbcodes für Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Standardwerte
SKIP_PUSH=false
LOCAL_ONLY=false

# Argument-Parsing
while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-push)
      SKIP_PUSH=true
      shift
      ;;
    --local-only)
      LOCAL_ONLY=true
      shift
      ;;
    *)
      echo "Unbekannte Option: $1"
      echo "Verwendung: $0 [--skip-push] [--local-only]"
      exit 1
      ;;
  esac
done

# Funktion für farbige Ausgabe
log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

# 1. Docker Images bauen
log_info "🐳 Building Docker images..."
cd /home/sb/github/ninko
docker compose build backend
log_success "Docker images built successfully"

# 2. Images taggen
log_info "🏷️  Tagging images..."
docker tag ninko-backend:latest natorus87/ninko-backend:latest
log_success "Images tagged successfully"

# 3. Zu Docker Hub pushen (optional)
if [ "$SKIP_PUSH" = false ] && [ "$LOCAL_ONLY" = false ]; then
  log_info "🚀 Pushing to Docker Hub..."
  docker push natorus87/ninko-backend:latest
  log_success "Images pushed to Docker Hub successfully"
else
  log_warning "Skipping Docker Hub push (--skip-push or --local-only flag)"
fi

# 4. Kubernetes Deployment (nur wenn nicht --local-only)
if [ "$LOCAL_ONLY" = false ]; then
  log_info "☸️  Deploying to Kubernetes..."
  kubectl apply -f k8s/backend/deployment.yaml -n ninko
  
  log_info "Waiting for rollout to complete..."
  if kubectl rollout status deployment/ninko-backend -n ninko --timeout=120s; then
    log_success "Kubernetes deployment successful"
  else
    log_error "Rollout failed or timed out"
    exit 1
  fi
  
  # Verifikation
  log_info "Verifying deployment..."
  echo -e "${BLUE}=== PODS ===${NC}"
  kubectl get pods -n ninko
  echo -e "${BLUE}=== SERVICES ===${NC}"
  kubectl get svc -n ninko
else
  log_info "📦 Starting local Docker Compose stack..."
  docker compose up -d --no-deps backend
  log_success "Local deployment successful"
  echo -e "${BLUE}=== CONTAINERS ===${NC}"
  docker compose ps
fi

# 5. Abschluss
log_success "🎉 Ninko backend deployed successfully!"
if [ "$LOCAL_ONLY" = false ]; then
  echo ""
  echo "Access the application at:"
  echo "- Local: http://localhost:8000"
  echo "- Kubernetes: Check IngressRoute configuration"
fi
