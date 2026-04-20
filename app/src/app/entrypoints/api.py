"""FastAPI hybrid-search API — Cloud Run Service entrypoint.

Endpoints:

* ``/search``   — candidate retrieval + optional LambdaRank rerank.
* ``/feedback`` — click / favorite / inquiry log sink.
* ``/jobs/check-retrain`` + ``/events/retrain`` — ranker retrain orchestration.

Rerank is opt-in via ``ApiSettings.enable_rerank``. Lifespan tries to resolve
+ load the latest booster from ``mlops.training_runs`` + GCS; load failures
log a warning and the API keeps running with ``booster=None`` (Phase 4
fallback, ``final_rank == lexical_rank``). That way a newly-deployed revision
stays up even if the training loop has not yet produced a model.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

from common.logging import configure_logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common import get_logger

from ..adapters import (
    BigQueryCandidateRetriever,
    BigQueryModelResolver,
    CloudRunJobRunner,
    DispatchModelSource,
    GcsModelSource,
    InMemoryTTLCacheStore,
    LocalModelSource,
    MeilisearchLexical,
    NoopCacheStore,
    NoopFeedbackRecorder,
    NoopLexicalSearch,
    NoopRankingLogPublisher,
    PubSubFeedbackRecorder,
    PubSubPublisher,
    PubSubRankingLogPublisher,
    create_retrain_queries,
)
from ..config import ApiSettings
from ..middleware import RequestLoggingMiddleware
from ..ports import (
    CacheStore,
    FeedbackRecorder,
    LexicalSearchPort,
    PredictionPublisher,
    RankingLogPublisher,
    TrainingJobRunner,
)
from ..schemas import (
    FeedbackRequest,
    FeedbackResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from ..services.model_store import load_model, resolve_model_uri
from ..services.ranking import normalize_search_cache_key, run_search
from ..services.retrain_policy import evaluate as evaluate_retrain

if TYPE_CHECKING:
    import lightgbm as lgb


def _build_retrain_publisher(settings: ApiSettings) -> PredictionPublisher | None:
    if not settings.retrain_topic:
        return None
    return PubSubPublisher(project_id=settings.project_id, topic=settings.retrain_topic)


def _build_ranking_log_publisher(settings: ApiSettings) -> RankingLogPublisher:
    if not settings.ranking_log_topic:
        return NoopRankingLogPublisher()
    return PubSubRankingLogPublisher(
        project_id=settings.project_id, topic=settings.ranking_log_topic
    )


def _build_feedback_recorder(settings: ApiSettings) -> FeedbackRecorder:
    if not settings.feedback_topic:
        return NoopFeedbackRecorder()
    return PubSubFeedbackRecorder(project_id=settings.project_id, topic=settings.feedback_topic)


def _build_candidate_retriever(settings: ApiSettings) -> BigQueryCandidateRetriever:
    embeddings_table = (
        f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
        f"{settings.bq_table_property_embeddings}"
    )
    features_table = (
        f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
        f"{settings.bq_table_property_features_daily}"
    )
    properties_table = (
        f"{settings.project_id}.{settings.bq_dataset_feature_mart}."
        f"{settings.bq_table_properties_cleaned}"
    )
    lexical: LexicalSearchPort
    if settings.meili_base_url:
        lexical = MeilisearchLexical(
            base_url=settings.meili_base_url,
            index_name=settings.meili_index_name,
            api_key=settings.meili_api_key,
            require_identity_token=settings.meili_require_identity_token,
        )
    else:
        lexical = NoopLexicalSearch()

    return BigQueryCandidateRetriever(
        project_id=settings.project_id,
        lexical=lexical,
        embeddings_table=embeddings_table,
        features_table=features_table,
        properties_table=properties_table,
    )


def _build_search_cache(settings: ApiSettings) -> CacheStore:
    if settings.search_cache_ttl_seconds <= 0:
        return NoopCacheStore()
    return InMemoryTTLCacheStore(
        maxsize=settings.search_cache_maxsize,
        default_ttl_seconds=settings.search_cache_ttl_seconds,
    )


def _try_load_booster(
    settings: ApiSettings, training_runs_table: str
) -> tuple[lgb.Booster | None, str | None]:
    """Resolve + materialize + load the latest booster. Returns (None, None) on any failure."""
    logger = get_logger("app")
    try:
        resolver = BigQueryModelResolver(
            project_id=settings.project_id,
            training_runs_table=training_runs_table,
        )
        uri = resolve_model_uri(override=settings.model_path_override, resolver=resolver)
        if uri is None:
            logger.warning(
                "enable_rerank=True but no training run is available; "
                "serving with rerank disabled (fallback to lexical_rank)"
            )
            return None, None
        local_dir = Path(settings.local_model_dir)
        local_dir.mkdir(parents=True, exist_ok=True)
        source = DispatchModelSource(gcs=GcsModelSource(), local=LocalModelSource())
        loaded = load_model(uri, local_dir, source)
    except Exception:
        logger.exception(
            "Booster load failed; serving with rerank disabled (fallback to lexical_rank)"
        )
        return None, None
    return loaded.booster, loaded.model_path


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
    logger = get_logger("app")
    settings = ApiSettings()

    training_runs_table = (
        f"{settings.project_id}.{settings.bq_dataset_mlops}.{settings.bq_table_training_runs}"
    )

    app.state.retrain_trigger_publisher = _build_retrain_publisher(settings)
    app.state.retrain_queries = create_retrain_queries(
        project_id=settings.project_id,
        training_runs_table=training_runs_table,
    )
    app.state.training_job_runner = CloudRunJobRunner(
        project_id=settings.project_id,
        region=settings.region,
        job_name="training-job",
    )

    # /search encoder + candidate retriever (Phase 4 baseline).
    if settings.enable_search:
        from common.embeddings import E5Encoder

        encoder_dir = Path(settings.encoder_model_dir) if settings.encoder_model_dir else None
        app.state.encoder = E5Encoder.load(model_dir=encoder_dir)
        app.state.candidate_retriever = _build_candidate_retriever(settings)
    else:
        app.state.encoder = None
        app.state.candidate_retriever = None

    # Phase 6 LambdaRank booster — optional. Load failure is not fatal.
    if settings.enable_search and settings.enable_rerank:
        booster, model_path = _try_load_booster(settings, training_runs_table)
    else:
        booster, model_path = None, None
    app.state.booster = booster
    app.state.model_path = model_path

    app.state.ranking_log_publisher = _build_ranking_log_publisher(settings)
    app.state.feedback_recorder = _build_feedback_recorder(settings)
    app.state.search_cache = _build_search_cache(settings)
    app.state.settings = settings
    app.state.training_runs_table = training_runs_table
    logger.info(
        "Startup complete; search_enabled=%s rerank_enabled=%s model_path=%s",
        settings.enable_search,
        booster is not None,
        model_path,
    )
    yield


def create_app() -> FastAPI:
    configure_logging()
    logger = get_logger("app")
    app = FastAPI(title="bq-first hybrid search API", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware, logger=logger)

    # `/livez` is the canonical liveness path. `/healthz` is also registered
    # for local-dev compatibility and existing tests, but Cloud Run's frontend
    # intercepts the literal path `/healthz` (Knative queue-proxy reserved
    # path) and returns its own HTML 404 before the request reaches the
    # container. Use `/livez` for any production probe.
    @app.get("/livez")
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(request: Request) -> JSONResponse:
        retriever = getattr(request.app.state, "candidate_retriever", None)
        if retriever is None:
            return JSONResponse({"status": "loading"}, status_code=503)
        booster = getattr(request.app.state, "booster", None)
        return JSONResponse(
            {
                "status": "ready",
                "search_enabled": True,
                "rerank_enabled": booster is not None,
                "model_path": getattr(request.app.state, "model_path", None),
            }
        )

    @app.post("/search", response_model=SearchResponse)
    def search(req: SearchRequest, request: Request) -> SearchResponse | JSONResponse:
        retriever = getattr(request.app.state, "candidate_retriever", None)
        encoder = getattr(request.app.state, "encoder", None)
        if retriever is None or encoder is None:
            return JSONResponse(
                {"detail": "/search disabled (enable_search=False or encoder missing)"},
                status_code=503,
            )
        request_id = cast(str, getattr(request.state, "request_id", uuid.uuid4().hex))
        settings: ApiSettings = request.app.state.settings
        search_cache: CacheStore = request.app.state.search_cache
        cache_key = normalize_search_cache_key(
            query=req.query,
            filters=req.filters.model_dump(),
            top_k=req.top_k,
        )
        cached = search_cache.get(cache_key)
        if cached is not None:
            cached_results = [SearchResultItem.model_validate(item) for item in cached["results"]]
            return SearchResponse(
                request_id=request_id,
                results=cached_results,
                model_path=cached.get("model_path"),
            )

        query_vec = encoder.encode_queries([req.query])[0]
        query_vector = [float(x) for x in query_vec]

        publisher: RankingLogPublisher = request.app.state.ranking_log_publisher
        booster = getattr(request.app.state, "booster", None)
        model_path = getattr(request.app.state, "model_path", None)
        pairs = run_search(
            retriever=retriever,
            publisher=publisher,
            request_id=request_id,
            query_text=req.query,
            query_vector=query_vector,
            filters=req.filters.model_dump(),
            top_k=req.top_k,
            booster=booster,
            model_path=model_path,
        )

        # Rebuild the per-candidate score lookup so SearchResultItem can carry it.
        # (run_search returns the ranked tuple list; the score list was emitted
        # to the publisher in lexical order.)
        score_by_id: dict[str, float] = {}
        if booster is not None:
            # Recompute scores for the truncated pairs — cheap (top_k ≤ 100) and
            # avoids threading a second list back through run_search.
            from ..services.ranking import _score_candidates

            returned_candidates = [cand for cand, _ in pairs]
            if returned_candidates:
                scores = _score_candidates(returned_candidates, booster)
                score_by_id = {
                    c.property_id: s for c, s in zip(returned_candidates, scores, strict=True)
                }

        results = [
            SearchResultItem(
                property_id=cand.property_id,
                final_rank=final_rank,
                lexical_rank=cand.lexical_rank,
                semantic_rank=cand.semantic_rank,
                me5_score=cand.me5_score,
                score=score_by_id.get(cand.property_id),
            )
            for cand, final_rank in pairs
        ]
        search_cache.set(
            cache_key,
            {
                "results": [r.model_dump() for r in results],
                "model_path": model_path,
            },
            settings.search_cache_ttl_seconds,
        )
        return SearchResponse(request_id=request_id, results=results, model_path=model_path)

    @app.post("/feedback", response_model=FeedbackResponse)
    def feedback(req: FeedbackRequest, request: Request) -> FeedbackResponse:
        recorder: FeedbackRecorder = request.app.state.feedback_recorder
        try:
            recorder.record(
                request_id=req.request_id,
                property_id=req.property_id,
                action=req.action,
            )
        except Exception:
            get_logger("app").exception("Feedback publish failed — continuing")
            return FeedbackResponse(accepted=False)
        return FeedbackResponse(accepted=True)

    @app.post("/jobs/check-retrain")
    def check_retrain(request: Request) -> JSONResponse:
        """Evaluate OR-conditions, publish retrain-trigger if any fires, return decision."""
        queries = request.app.state.retrain_queries
        decision = evaluate_retrain(queries)
        response = {
            "should_retrain": decision.should_retrain,
            "reasons": decision.reasons,
            "feedback_rows_since_last": decision.feedback_rows_since_last,
            "ndcg_current": decision.ndcg_current,
            "ndcg_week_ago": decision.ndcg_week_ago,
            "last_run_finished_at": (
                decision.last_run_finished_at.isoformat() if decision.last_run_finished_at else None
            ),
        }

        if decision.should_retrain:
            trigger: PredictionPublisher | None = getattr(
                request.app.state, "retrain_trigger_publisher", None
            )
            if trigger is not None:
                try:
                    trigger.publish({"reasons": decision.reasons})
                    response["published"] = True
                except Exception:
                    get_logger("app").exception("Failed to publish retrain-trigger")
                    response["published"] = False
        return JSONResponse(response)

    @app.post("/events/retrain")
    def events_retrain(request: Request) -> JSONResponse:
        """Eventarc target — receives CloudEvents from retrain-trigger topic,
        then starts the Cloud Run Job `training-job`.
        """
        runner: TrainingJobRunner = request.app.state.training_job_runner
        execution = runner.start()
        get_logger("app").info("Kicked training-job: %s", execution)
        return JSONResponse({"execution": execution})

    return app


app = create_app()
