SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

# Absolute paths keep targets idempotent regardless of invocation cwd.
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
INFRA := $(ROOT)/infra

# Project-wide non-credential settings live in env/config/setting.yaml so
# Python (scripts/_common.py) and Make read from one source of truth. We
# parse the flat key:value file with awk (faster than `uv run python` and
# already a Make hard dep for the help target).
SETTINGS_FILE := $(ROOT)/env/config/setting.yaml
_yaml_get = $(strip $(shell awk -F: '/^$(1):/ {gsub(/^[ "'\'']+|[ "'\'']+$$/,"",$$2); print $$2; exit}' $(SETTINGS_FILE)))

PROJECT_ID    ?= $(call _yaml_get,project_id)
REGION        ?= $(call _yaml_get,region)
API_SERVICE   ?= $(call _yaml_get,api_service)
TRAINING_JOB  ?= $(call _yaml_get,training_job)
ARTIFACT_REPO ?= $(call _yaml_get,artifact_repo)
VERTEX_LOCATION ?= $(call _yaml_get,vertex_location)
PIPELINE_ROOT_BUCKET ?= $(call _yaml_get,pipeline_root_bucket)
PIPELINE_TEMPLATE_GCS_PATH ?= $(call _yaml_get,pipeline_template_gcs_path)

# Override-able via CLI: `make tf-plan GITHUB_REPO=other/repo ONCALL_EMAIL=...`
GITHUB_REPO   ?= $(call _yaml_get,github_repo)
ONCALL_EMAIL  ?= $(call _yaml_get,oncall_email)

# Local model path produced by `make train-smoke-persist`.
MODEL_PATH_OVERRIDE ?= /tmp/bq-first-smoke-model.txt

# Scripts and their make-target wrappers must stay in lockstep — adding a new
# target should usually mean adding a sibling script under scripts/ or
# scripts/ops/ rather than inlining shell here.
export PROJECT_ID REGION API_SERVICE TRAINING_JOB ARTIFACT_REPO VERTEX_LOCATION PIPELINE_ROOT_BUCKET PIPELINE_TEMPLATE_GCS_PATH

.PHONY: help doctor sync test lint fmt fmt-check typecheck check \
        check-layers sync-dataform-config \
        tf-bootstrap tf-init tf-validate tf-fmt tf-fmt-fix tf-plan \
        setup-model-monitoring setup-pipeline-schedule \
        deploy-all destroy-all seed-test seed-test-clean \
        train-smoke train-smoke-persist api-dev clean \
        docker-auth deploy-api-local deploy-training-job-local \
        ops-api-url ops-daily ops-livez ops-search ops-ranking ops-feedback ops-enable-search \
        ops-skew-latest ops-search-volume ops-runs-recent \
	ops-skew-run ops-train-now ops-pipeline-run ops-promote-reranker ops-reload-api \
        ops-check-retrain ops-bq-scan-top ops-label-seed

help: ## Show this help
	@echo "First-time setup:  see README.md §セットアップ (run 'make doctor' to verify tools)"
	@echo "Quick start:       make sync && make check && make train-smoke"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} \
		/^[a-zA-Z0-9_-]+:.*##/ { printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)

doctor: ## Verify that prerequisite tools are installed
	uv run python -m scripts.setup.doctor

# ----- Python workspace -----

sync: ## uv sync (all workspace packages + dev group)
	uv sync --all-packages --dev

test: ## Run pytest across the workspace
	uv run pytest

lint: ## ruff check
	uv run ruff check .

fmt: ## ruff format (writes)
	uv run ruff format .

fmt-check: ## ruff format --check
	uv run ruff format --check .

typecheck: ## mypy strict
	uv run mypy common/src app/src jobs/src

check: lint fmt-check typecheck test ## Run all CI-equivalent checks

sync-dataform-config: ## Regenerate definitions/workflow_settings.yaml from env/config/setting.yaml
	uv run python -m scripts.config.sync_dataform

check-layers: ## AST-based layer boundary check (Ports / pure logic must not import concrete adapters or SDKs)
	uv run python -m scripts.checks.layers

# ----- Terraform -----

tf-bootstrap: ## Phase 0: enable APIs + create tfstate bucket (idempotent, needs project owner rights)
	uv run python -m scripts.setup.tf_bootstrap

tf-init: ## terraform init (with tfstate bucket preflight check)
	uv run python -m scripts.setup.tf_init

tf-validate: ## terraform validate (backend-less, works offline)
	terraform -chdir=$(INFRA) init -backend=false -upgrade=false >/dev/null
	terraform -chdir=$(INFRA) validate

tf-fmt: ## terraform fmt --check
	terraform -chdir=$(INFRA) fmt -check -diff

tf-fmt-fix: ## terraform fmt (writes)
	terraform -chdir=$(INFRA) fmt

tf-plan: ## terraform plan (requires GITHUB_REPO + ONCALL_EMAIL; saves infra/tfplan)
	uv run python -m scripts.setup.tf_plan

setup-model-monitoring: ## Print resolved Vertex Model Monitoring setup payload
	uv run python -m scripts.setup.setup_model_monitoring

setup-pipeline-schedule: ## Print resolved Vertex Pipeline schedule setup payload
	uv run python -m scripts.setup.create_schedule

deploy-all: ## End-to-end provisioning + search-api rollout (tf-bootstrap → apply → deploy-api-local)
	uv run python -m scripts.setup.deploy_all

destroy-all: ## Tear down every Terraform-managed resource (no prompt — PDCA loop, pair with deploy-all)
	uv run python -m scripts.setup.destroy_all

seed-test: ## Insert 5 test properties into feature_mart.{properties_cleaned,property_features_daily,property_embeddings} for PDCA smoke
	uv run python -m scripts.setup.seed_minimal

seed-test-clean: ## Drop the test seed data (benign if absent). Same cleanup runs as step 1/3 of `make destroy-all`
	uv run python -m scripts.setup.seed_minimal_clean

# ----- App / Job smoke commands (local) -----

train-smoke: ## Dry-run the ranker training job locally (synthetic data, no GCS/BQ)
	uv run --package jobs rank-train --dry-run

train-smoke-persist: ## Dry-run ranker trainer and copy the model to $(MODEL_PATH_OVERRIDE)
	uv run --package jobs rank-train --dry-run --save-to "$(MODEL_PATH_OVERRIDE)"

api-dev: ## Start uvicorn locally (rerank-free /search requires ENABLE_SEARCH=1 + BQ creds)
	ENABLE_SEARCH=false uv run --package app uvicorn app.entrypoints.api:app --reload

# ----- Local deploy path (bypasses CI; uses Cloud Build) -----

docker-auth: ## (Optional) configure local docker for Artifact Registry — not needed when using Cloud Build
	gcloud auth configure-docker $(REGION)-docker.pkg.dev --quiet

deploy-api-local: ## Cloud Build + `gcloud run deploy` search-api
	uv run python -m scripts.deploy.api_local

deploy-training-job-local: ## Deprecated: training moved to Vertex Pipelines
	@echo "training-job は廃止済みです。make ops-train-now を使ってください。"

# ----- Housekeeping -----

clean: ## Remove caches (.venv, .terraform, pyc)
	rm -rf .venv $(INFRA)/.terraform
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) -prune -exec rm -rf {} +

# ----- GCP operations (see docs/04_運用.md §3) -----
# Each target is a thin wrapper around scripts/ops/*.sh or scripts/sql/*.sql.

ops-api-url: ## Print the search-api Cloud Run URL
	@gcloud run services describe $(API_SERVICE) --project=$(PROJECT_ID) --region=$(REGION) --format='value(status.url)'

ops-daily: ops-skew-latest ops-search-volume ops-runs-recent ## Run the 3 core daily checks

ops-skew-latest: ## Today's per-feature skew detection results (validation_results)
	bq query --use_legacy_sql=false --project_id=$(PROJECT_ID) < scripts/sql/skew_latest.sql

ops-search-volume: ## /search request volume over the last 24h
	bq query --use_legacy_sql=false --project_id=$(PROJECT_ID) < scripts/sql/search_volume.sql

ops-runs-recent: ## Last 5 LightGBM LambdaRank training runs
	bq query --use_legacy_sql=false --project_id=$(PROJECT_ID) < scripts/sql/runs_recent.sql

ops-skew-run: ## Ad-hoc execution of monitoring/validate_feature_skew.sql
	bq query --use_legacy_sql=false --project_id=$(PROJECT_ID) < monitoring/validate_feature_skew.sql

ops-bq-scan-top: ## Top 20 BQ scans in the last 7 days (cost audit)
	bq query --use_legacy_sql=false --project_id=$(PROJECT_ID) < scripts/sql/bq_scan_top.sql

ops-train-now: ## Submit train pipeline to Vertex AI
	uv run --package pipelines compile-pipelines --target train --output-dir dist/pipelines --submit --project-id $(PROJECT_ID) --location $(VERTEX_LOCATION) --pipeline-root gs://$(PIPELINE_ROOT_BUCKET)/runs --service-account sa-pipeline@$(PROJECT_ID).iam.gserviceaccount.com

ops-pipeline-run: ## Submit a pipeline manually: TARGET=embed|train PARAM='key=value'
	uv run --package pipelines compile-pipelines --target $${TARGET:-train} --output-dir dist/pipelines --submit --project-id $(PROJECT_ID) --location $(VERTEX_LOCATION) --pipeline-root gs://$(PIPELINE_ROOT_BUCKET)/runs --service-account sa-pipeline@$(PROJECT_ID).iam.gserviceaccount.com $${PARAM:+--parameter $$PARAM}

ops-promote-reranker: ## Print or apply reranker promotion plan: VERSION=vN APPLY=1
	uv run python -m scripts.ops.promote reranker $${VERSION:-v1} $${APPLY:+--apply}

ops-reload-api: ## Bump FORCE_RELOAD env so search-api picks up the latest model
	gcloud run services update $(API_SERVICE) --project=$(PROJECT_ID) --region=$(REGION) --update-env-vars="FORCE_RELOAD=$$(date +%s)"

ops-enable-search: ## Flip search-api to Vertex endpoint mode (set ENCODER_ENDPOINT_ID, optional RERANKER_ENDPOINT_ID)
	gcloud run services update $(API_SERVICE) --project=$(PROJECT_ID) --region=$(REGION) --update-env-vars="ENABLE_SEARCH=true,ENABLE_RERANK=$${RERANKER_ENDPOINT_ID:+true},VERTEX_LOCATION=$(VERTEX_LOCATION),VERTEX_ENCODER_ENDPOINT_ID=$${ENCODER_ENDPOINT_ID:?set ENCODER_ENDPOINT_ID},VERTEX_RERANKER_ENDPOINT_ID=$${RERANKER_ENDPOINT_ID:-}"

ops-livez: ## Hit /livez on the deployed search-api (IAM-gated)
	uv run python -m scripts.ops.livez_check

ops-search: ## POST /search smoke (override QUERY/TOP_K/MAX_RENT env vars)
	uv run python -m scripts.ops.search_check

ops-ranking: ## POST /search and inspect lexical_rank / final_rank / score / me5_score
	uv run python -m scripts.ops.ranking_check

ops-feedback: ## /search → /feedback round-trip (publisher path smoke)
	uv run python -m scripts.ops.feedback_check

ops-label-seed: ## Seed feedback events (click/favorite/inquiry) against /search
	uv run python -m scripts.ops.training_label_seed

ops-check-retrain: ## POST /jobs/check-retrain with OIDC; pipe to jq
	uv run python -m scripts.ops.check_retrain
