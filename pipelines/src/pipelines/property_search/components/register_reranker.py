"""KFP component: upload and optionally deploy a reranker model."""

from kfp import dsl


@dsl.component(
    base_image="python:3.12",
    packages_to_install=["google-cloud-aiplatform>=1.71,<2"],
)
def register_reranker(
    project_id: str,
    vertex_location: str,
    model_display_name: str,
    endpoint_resource_name: str,
    serving_container_image_uri: str,
    service_account: str,
    traffic_new_percentage: int,
    deploy_machine_type: str,
    model_artifact: dsl.Input[dsl.Model],
) -> str:
    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=vertex_location)
    uploaded_model = aiplatform.Model.upload(
        display_name=model_display_name,
        artifact_uri=model_artifact.uri,
        serving_container_image_uri=serving_container_image_uri,
        serving_container_predict_route="/predict",
        serving_container_health_route="/health",
        serving_container_ports=[8080],
        version_aliases=["staging"],
        sync=True,
    )
    if endpoint_resource_name:
        endpoint = aiplatform.Endpoint(endpoint_name=endpoint_resource_name)
        uploaded_model.deploy(
            endpoint=endpoint,
            deployed_model_display_name=model_display_name,
            machine_type=deploy_machine_type,
            min_replica_count=1,
            max_replica_count=5,
            traffic_percentage=traffic_new_percentage,
            service_account=service_account or None,
            sync=True,
        )
    return uploaded_model.resource_name
