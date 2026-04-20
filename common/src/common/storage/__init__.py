"""Storage adapters (GCS)."""

from .gcs_artifact_store import GcsPrefix, download_file, model_prefix, upload_directory

__all__ = ["GcsPrefix", "download_file", "model_prefix", "upload_directory"]
