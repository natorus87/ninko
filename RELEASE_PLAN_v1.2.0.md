# Ninko v1.2.0 Release Plan

## Overview
Major feature release with 122 commits since v1.1.0

## Version Bumps
- **Application Version**: 1.1.0 → 1.2.0
- **Helm Chart**: 0.6.2 → 0.7.0
- **Docker Image**: natorus87/ninko-backend:v1.2.0

## Release Notes Structure

### 🎉 New Features (Major)

#### 1. DataViz Core Module ⭐
- **Chart Types**: Line, Bar, Pie, Scatter, Area diagrams
- **Engines**: matplotlib (static) + Plotly (interactive)
- **Mermaid Support**: Flowcharts, Sequence, Gantt, Class, State diagrams
- **APIs**: `/chart`, `/mermaid`, `/chart/types`, `/chart/interactive`
- **Frontend**: Dashboard tab with Chart Generator, Mermaid editor, History
- **Dependencies**: matplotlib, plotly, kaleido

#### 2. Telegram Bot Overhaul
- OpenClaw-style Streaming (Preview → Edit)
- Pairing/Allowlist System
- Custom Commands menu
- Reply Threading
- 👀 Ack reaction for immediate feedback
- Safeguard confirmation buttons fixed

#### 3. ToolRegistry System
- Centralized tool metadata registry
- Readonly/destructive flags
- Required binaries/envs validation
- Auto-discovery from module tools

#### 4. AlertStateManager
- Redis-based alert tracking
- Alert deduplication
- REST API for alert management
- Settings UI with alerts table
- 10-language i18n support

#### 5. Skills System
- SKILL.md format with YAML frontmatter
- Hot-reloadable from persistent volume
- Settings page with Skills tab
- Marketplace integration

### 🔧 Architecture Improvements

#### 6. DeerFlow-Inspired Middleware
- Task tracking and error logging
- LoopDetectionMiddleware with TTL-based cleanup
- StreamBridge for gateway mode
- Harness/app boundary scaffolding

#### 7. Gateway Mode
- RunManager with DoS protection
- StreamBridge for multi-tenant streaming
- Pipeline execution improvements

#### 8. Mobile Responsive UI
- Hamburger menu for mobile
- Responsive layout adaptations

#### 9. Knowledge Graph & RAG Optimization
- Memory scoring improvements
- PDF generation support
- ChromaDB optimizations

### 🔒 Security Hardening

#### Critical Fixes
- **CWE-326**: Vault PBKDF2 migration with transparent dual-key layer
- **CWE-256**: GitHub token encryption in Redis (Fernet)
- **XSS Mitigation**: DOMPurify sanitization in formatText()
- **CWE-22**: Path traversal fixes in ZIP extraction
- **CSP**: Content-Security-Policy meta tag added

#### Auth & Session
- Unicode normalization for passwords
- Force bootstrap password update
- Session security improvements
- Missing auth checks added

### 📦 Module Updates

#### New Integrations
- **OpenProject**: Full project management integration
- **Redmine HRM**: Vacation, sick leave, attendance tools
- **DataAnalysisSubagent**: Tier 2.5 for data-intensive queries

#### Improvements
- Professional SVG icons for all 42 modules
- Module CHANGELOGs added
- SSL verification toggles
- Connection form fields in Settings UI
- Version tracking and update system

### 🐛 Bug Fixes
- Telegram safeguard confirmation buttons
- Frontend marked.js + DOMPurify bundling (offline/K8s fix)
- OCR resource cleanup (Image.open context manager)
- Agent memory leaks fixed
- Redis chat history limited to 100 messages
- Safeguard pre-filter for short messages

## Files Changed (15 files in DataViz commit)
```
.gitignore
backend/core/tool_registry.py
backend/modules/dataviz/* (8 new files)
backend/requirements.txt
charts/ninko/templates/backend/deployment.yaml
charts/ninko/values.yaml
frontend/app.js
k8s/backend/deployment.yaml
```

## Build & Deploy Steps

### 1. Version Bump Files
- [ ] Update `charts/ninko/Chart.yaml`: version 0.7.0, appVersion 1.2.0
- [ ] Update `backend/main.py` or version file if exists
- [ ] Update `CHANGELOG.md` at root

### 2. Build Image
```bash
docker compose build backend
docker tag ninko-backend:latest natorus87/ninko-backend:v1.2.0
docker tag ninko-backend:latest natorus87/ninko-backend:latest
docker push natorus87/ninko-backend:v1.2.0
docker push natorus87/ninko-backend:latest
```

### 3. Create Git Tag
```bash
git tag -a v1.2.0 -m "Release v1.2.0: DataViz, Telegram Overhaul, Security Hardening"
git push origin v1.2.0
```

### 4. GitHub Release
- Create release from tag v1.2.0
- Paste formatted release notes
- Attach CHANGELOG

### 5. Deploy Production
```bash
kubectl rollout restart deployment/ninko-backend -n ninko
kubectl rollout status deployment/ninko-backend -n ninko --timeout=120s
```

## Breaking Changes
None - all changes are backward compatible.

## Migration Notes
- Vault secrets auto-migrate to PBKDF2 (transparent)
- Skills auto-discover from `data/skills/`
- DataViz enabled by default via env var

## Test Checklist
- [ ] DataViz charts render correctly
- [ ] Telegram bot commands work
- [ ] Safeguard confirmations functional
- [ ] Module installations from Marketplace
- [ ] Alert system operational
- [ ] Mobile UI responsive
