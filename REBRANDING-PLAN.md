# ollyScale Rebranding Plan

## Overview

Complete rebranding from TinyOlly to ollyScale, including licensing changes, container/chart naming
strategy, and CI/CD improvements for future forks.

## Licensing Strategy

### Phase 1: License Files

- [x] Rename `LICENSE` to `LICENSE-BSD3-ORIGINAL` (preserve TinyOlly's original license)
- [ ] Create `LICENSE` with AGPL-3.0
- [ ] Create `NOTICE` file acknowledging TinyOlly origins and dual licensing
- [ ] Create `LICENSE-HEADER-AGPL.txt` template for new/modified files
- [ ] Create `LICENSE-HEADER-BSD3.txt` template for original TinyOlly files

### Phase 2: File Headers

**Original TinyOlly files (keep BSD-3-Clause header):**

- Files we didn't significantly modify from upstream
- Add comment noting "Originally from TinyOlly project"

**Modified/New files (add AGPL header):**

- Files we created: `.kind/`, rebranding configs, new features
- Files significantly modified (>30% changes)
- Include: "Based on TinyOlly (BSD-3-Clause), see LICENSE-BSD3-ORIGINAL"

## Naming Strategy

### Container/Chart Function-Based Naming (RECOMMENDED)

**Benefit:** Future forks can use our automation without rebranding
**Approach:** Use generic functional names in containers/charts, brand only in docs/UI

**Container Images:**

- `tinyolly/ui` → `observability-platform/ui` or keep `ollyscale/ui`
- `tinyolly/otlp-receiver` → `observability-platform/otlp-receiver`
- `tinyolly/opamp-server` → `observability-platform/opamp-server`

**Helm Charts:**

- `tinyolly` → `observability-platform` or `ollyscale`
- `tinyolly-demos` → `observability-demos`
- `tinyolly-demo-otel-agent` → `otel-agent-demo`

**Decision Point:** Should we use brand-neutral names or ollyScale brand?

- Option A: `observability-platform/*` (fork-friendly)
- Option B: `ollyscale/*` (clear branding)
- **Recommendation:** Option A for containers, Option B for marketing materials

### Kubernetes Resources

- Namespace: `tinyolly` → `observability` or `ollyscale`
- Service names: functional (ui, receiver, opamp-server)
- Deployment names: match service names

## Rebranding Checklist

### 1. Documentation & Marketing

- [ ] `README.md` - Add "Origins" section, update all references
- [ ] `CONTRIBUTING.md` - Update repository URLs, project name
- [ ] `docs/` directory - All markdown files
- [ ] `docs/images/` - Logo files (tinyollytitle.png, etc.)
- [ ] `mkdocs.yml` - Site name, repo URL
- [ ] Repository description on GitHub
- [ ] Social media preview image

### 2. CI/CD & Automation Scripts

**Use Environment Variables Strategy:**

```bash
# Instead of hardcoded:
REPO="tinyolly/tinyolly"

# Use:
GH_ORG="${GH_ORG:-ollyscale}"
GH_REPO="${GH_REPO:-observability-platform}"
CONTAINER_REGISTRY="${CONTAINER_REGISTRY:-ghcr.io}"
```

**Files to Update:**

- [ ] `.github/workflows/*.yml` - All workflow files
- [ ] `.github/dependabot.yml` - Directory paths, labels
- [ ] `scripts/build/*.sh` - Image names, registry paths
- [ ] `scripts/release/*.sh` - Release automation
- [ ] `charts/build-and-push-local.sh` - Local build script
- [ ] `charts/deploy-to-argocd.sh` - Deployment automation
- [ ] `Makefile` - All targets and variables

### 3. Helm Charts

- [ ] `charts/tinyolly/Chart.yaml` - name, description, home, sources
- [ ] `charts/tinyolly/values.yaml` - image repositories, names
- [ ] `charts/tinyolly/templates/*.yaml` - labels, annotations, names
- [ ] `charts/tinyolly-demos/Chart.yaml`
- [ ] `charts/tinyolly-demos/values.yaml`
- [ ] `charts/tinyolly-demo-otel-agent/Chart.yaml`
- [ ] Consider: Rename chart directories to function-based names

### 4. Kubernetes/KIND Configuration

- [ ] `.kind/modules/main/main.tf` - Cluster name, namespaces
- [ ] `.kind/modules/main/variables.tf` - Variable names, defaults
- [ ] `.kind/modules/tinyolly/*.tf` - Module name, resource names
- [ ] `.kind/modules/tinyolly/argocd-applications/observability/*.yaml`
- [ ] `.kind/terraform.auto.tfvars` - Variable values
- [ ] Consider: Rename `.kind/modules/tinyolly/` to `.kind/modules/observability/`

### 5. Source Code - Python

**Backend (`apps/tinyolly/`):**

- [ ] Directory name: `apps/tinyolly/` → `apps/observability-platform/` or `apps/ollyscale/`
- [ ] `app/__init__.py` - Service name, metadata
- [ ] `app/main.py` - FastAPI title, description, version
- [ ] `models.py` - Model names if branded
- [ ] `requirements.txt` - Package names if published
- [ ] Import statements across all Python files
- [ ] Add AGPL headers to modified files

### 6. Source Code - TypeScript/JavaScript

**Frontend (`apps/tinyolly-ui/`):**

- [ ] Directory name: `apps/tinyolly-ui/` → `apps/ui/`
- [ ] `package.json` - name, description, repository
- [ ] `src/` - All TypeScript imports, API endpoints
- [ ] Page titles, branding text in UI
- [ ] Add AGPL headers to modified files

### 7. Source Code - Go

**OpAMP Server (`apps/opamp-server/`):**

- [ ] `go.mod` - module path
- [ ] `main.go` - Service name, logging
- [ ] Add AGPL headers if modified

### 8. Docker & Containers

- [ ] `docker/dockerfiles/Dockerfile.tinyolly-ui` - Rename, update labels
- [ ] `docker/dockerfiles/Dockerfile.tinyolly-otlp-receiver` - Rename
- [ ] `docker/dockerfiles/Dockerfile.opamp-server` - Update labels
- [ ] `docker/apps/` - Build context references
- [ ] Container labels: `org.opencontainers.image.*`

### 9. Configuration Files

- [ ] `config/otelcol/` - Config file comments, service names
- [ ] `pyproject.toml` - Project name, URLs if used
- [ ] `release-please-config.json` - Package names, paths
- [ ] `.gitignore` - Path references
- [ ] `renovate.json` - Labels, automerge rules

### 10. Demo Applications

- [ ] `apps/demo/` - Service names, endpoints
- [ ] `apps/demo-otel-agent/` - Configuration references

## Implementation Phases

### Phase 1: Foundation (Licensing & Core Docs)

1. Create license files (AGPL, NOTICE)
2. Create header templates
3. Update README with origins section
4. Update main documentation

### Phase 2: Infrastructure (CI/CD & Automation)

1. Update Makefile with variables
2. Update GitHub workflows with GH_ORG/GH_REPO
3. Update build scripts with parameterization
4. Test local builds work

### Phase 3: Kubernetes & Charts (Technical Foundation)

1. Decide: Function-based vs. branded names
2. Update Helm chart names/values
3. Update Kubernetes manifests
4. Update Terraform configurations
5. Test deployment to KIND cluster

### Phase 4: Source Code (Application Layer)

1. Rename source directories
2. Update imports and namespaces
3. Add AGPL headers to modified files
4. Update package configurations
5. Test application builds

### Phase 5: Validation & Testing

1. Full build test (images + charts)
2. Deployment test to local KIND
3. Verify all services running
4. Check logs for old references
5. Test OTel Demo still works

### Phase 6: Polish & Documentation

1. Update all remaining docs
2. Create migration guide for fork users
3. Update screenshots/demos if branded
4. Final review for missed references

## Testing Strategy

After each phase:

```bash
# 1. Check for remaining references
grep -r "TinyOlly\|tinyolly" . --exclude-dir=.git --exclude-dir=node_modules \
  --exclude="REBRANDING-PLAN.md" --exclude="LICENSE-BSD3-ORIGINAL"

# 2. Test build
make deploy

# 3. Test deployment
kubectl get po -A | grep -v Running

# 4. Test functionality
# Access UI, send test telemetry, verify data flow
```

## Variables to Parameterize

### Environment Variables for CI/CD

```bash
# Organization & Repository
GH_ORG="${GH_ORG:-ollyscale}"
GH_REPO="${GH_REPO:-observability-platform}"

# Container Registry
CONTAINER_REGISTRY="${CONTAINER_REGISTRY:-ghcr.io}"
CONTAINER_ORG="${CONTAINER_ORG:-$GH_ORG}"

# Helm/OCI Registry
HELM_REGISTRY="${HELM_REGISTRY:-ghcr.io}"
HELM_ORG="${HELM_ORG:-$GH_ORG}"

# Branding (for forks)
PROJECT_NAME="${PROJECT_NAME:-ollyScale}"
PROJECT_NAME_LOWER="${PROJECT_NAME_LOWER:-ollyscale}"

# Kubernetes
K8S_NAMESPACE="${K8S_NAMESPACE:-observability}"
```

### Makefile Variables

```makefile
# Project configuration
PROJECT_NAME ?= ollyScale
PROJECT_SLUG ?= ollyscale
GH_ORG ?= ollyscale
GH_REPO ?= observability-platform

# Container configuration
REGISTRY ?= ghcr.io
REGISTRY_ORG ?= $(GH_ORG)
IMAGE_PREFIX ?= $(REGISTRY)/$(REGISTRY_ORG)

# Kubernetes
CLUSTER_NAME ?= $(PROJECT_SLUG)
NAMESPACE ?= observability
```

## Fork-Friendly Design Principles

1. **Parameterize Everything:** No hardcoded org/repo names in automation
2. **Functional Naming:** Container/chart names describe function, not brand
3. **Docs Separate from Code:** Brand only in docs, not in technical names
4. **Clear Origins:** Always acknowledge TinyOlly in NOTICE file
5. **License Clarity:** Dual licensing clearly documented

## Risk Mitigation

### Breaking Changes

- Database keys (Redis) may contain old names → Migration needed?
- API endpoints might be hardcoded in client code
- DNS/hostnames in ingress configurations

### Rollback Plan

- Keep branch for 1:1 comparison
- Tag pre-rebrand state: `git tag pre-ollyscale-rebrand`
- Document all namespace/name changes for troubleshooting

## Decision Log

### Decisions Needed

1. **Container naming:** Function-based (`observability-platform/*`) or branded (`ollyscale/*`)?
2. **Kubernetes namespace:** `observability`, `ollyscale`, or keep `tinyolly`?
3. **Helm chart names:** Rebrand or function-based?
4. **Python package name:** If publishing to PyPI, what name?
5. **Repository name:** Keep `tinyolly` or rename to `ollyscale` or `observability-platform`?

### Decisions Made

- **License:** AGPL-3.0 for new/modified code, preserve BSD-3-Clause for original
- **Approach:** Systematic phase-by-phase with testing between phases
- **CI/CD:** Parameterize all org/repo/registry references

## Notes

- This document will be updated as we progress
- Each completed item will be checked off
- Any issues or blockers will be documented here
- Consider creating migration guide for existing TinyOlly users
