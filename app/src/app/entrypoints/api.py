"""FastAPI hybrid-search API — Cloud Run Service entrypoint.

Cloud Run keeps only retrieval / orchestration concerns. Query embeddings and
rerank scoring are delegated to Vertex AI Endpoints when configured.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from common.logging import configure_logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common import get_logger

from ..adapters import (
    BigQueryCandidateRetriever,
    CloudRunJobRunner,
    InMemoryTTLCacheStore,
    MeilisearchLexical,
    NoopCacheStore,
    NoopFeedbackRecorder,
    NoopLexicalSearch,
    NoopRankingLogPublisher,
    PubSubFeedbackRecorder,
    PubSubPublisher,
    PubSubRankingLogPublisher,
    VertexEndpointEncoder,
    VertexEndpointReranker,
    create_retrain_queries,
)
from ..config import ApiSettings
from ..middleware import RequestLoggingMiddleware
from ..ports import (
    CacheStore,
    EncoderClient,
    FeedbackRecorder,
    LexicalSearchPort,
    PredictionPublisher,
    RankingLogPublisher,
    RerankerClient,
    TrainingJobRunner,
)
from ..schemas import (
    FeedbackRequest,
    FeedbackResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from ..services.ranking import normalize_search_cache_key, run_search
from ..services.retrain_policy import evaluate as evaluate_retrain


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


def _build_encoder_client(settings: ApiSettings) -> tuple[EncoderClient | None, str | None]:
    logger = get_logger("app")
    if not settings.vertex_encoder_endpoint_id:
        logger.warning("ENABLE_SEARCH=true but VERTEX_ENCODER_ENDPOINT_ID is empty")
        return None, None
    try:
        client = VertexEndpointEncoder(
            project_id=settings.project_id,
            location=settings.vertex_location,
            endpoint_id=settings.vertex_encoder_endpoint_id,
            timeout_seconds=settings.vertex_predict_timeout_seconds,
        )
    except Exception:
        logger.exception("Failed to initialize Vertex encoder endpoint client")
        return None, None
    return client, client.endpoint_name


def _build_reranker_client(settings: ApiSettings) -> tuple[RerankerClient | None, str | None]:
    logger = get_logger("app")
    if not settings.enable_rerank:
        return None, None
    if not settings.vertex_reranker_endpoint_id:
        logger.warning("ENABLE_RERANK=true but VERTEX_RERANKER_ENDPOINT_ID is empty")
        return None, None
    try:
        client = VertexEndpointReranker(
            project_id=settings.project_id,
            location=settings.vertex_location,
            endpoint_id=settings.vertex_reranker_endpoint_id,
            timeout_seconds=settings.vertex_predict_timeout_seconds,
        )
    except Exception:
        logger.exception("Failed to initialize Vertex reranker endpoint client")
        return None, None
    return client, client.endpoint_name


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

    if settings.enable_search:
        encoder_client, encoder_model_path = _build_encoder_client(settings)
        app.state.candidate_retriever = _build_candidate_retriever(settings)
        app.state.encoder_client = encoder_client
        app.state.encoder_model_path = encoder_model_path
    else:
        app.state.candidate_retriever = None
        app.state.encoder_client = None
        app.state.encoder_model_path = None

    reranker_client, model_path = _build_reranker_client(settings)
    app.state.reranker_client = reranker_client
    app.state.model_path = model_path

    app.state.ranking_log_publisher = _build_ranking_log_publisher(settings)
    app.state.feedback_recorder = _build_feedback_recorder(settings)
    app.state.search_cache = _build_search_cache(settings)
    app.state.settings = settings
    app.state.training_runs_table = training_runs_table
    logger.info(
        "Startup complete; search_enabled=%s rerank_enabled=%s model_path=%s",
        settings.enable_search,
        reranker_client is not None,
        model_path,
    )
    yield


def create_app() -> FastAPI:
    configure_logging()
    logger = get_logger("app")
    app = FastAPI(title="vertex-backed hybrid search API", lifespan=lifespan)
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
        encoder_client = getattr(request.app.state, "encoder_client", None)
        if retriever is None or encoder_client is None:
            return JSONResponse({"status": "loading"}, status_code=503)
        reranker = getattr(request.app.state, "reranker_client", None)
        return JSONResponse(
            {
                "status": "ready",
                "search_enabled": True,
                "rerank_enabled": reranker is not None,
                "model_path": getattr(reranker, "model_path", None),
            }
        )

    @app.post("/search", response_model=SearchResponse)
    def search(req: SearchRequest, request: Request) -> SearchResponse | JSONResponse:
        retriever = getattr(request.app.state, "candidate_retriever", None)
        encoder_client = getattr(request.app.state, "encoder_client", None)
        if retriever is None or encoder_client is None:
            return JSONResponse(
                {"detail": "/search disabled (enable_search=False or Vertex encoder missing)"},
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

        query_vector = encoder_client.embed(req.query, "query")

        publisher: RankingLogPublisher = request.app.state.ranking_log_publisher
        reranker = getattr(request.app.state, "reranker_client", None)
        model_path = getattr(reranker, "model_path", getattr(request.app.state, "model_path", None))
        ranked = run_search(
            retriever=retriever,
            publisher=publisher,
            request_id=request_id,
            query_text=req.query,
            query_vector=query_vector,
            filters=req.filters.model_dump(),
            top_k=req.top_k,
            reranker=reranker,
            model_path=model_path,
        )

        results = [
            SearchResultItem(
                property_id=item.candidate.property_id,
                final_rank=item.final_rank,
                lexical_rank=item.candidate.lexical_rank,
                semantic_rank=item.candidate.semantic_rank,
                me5_score=item.candidate.me5_score,
                score=item.score,
            )
            for item in ranked
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
