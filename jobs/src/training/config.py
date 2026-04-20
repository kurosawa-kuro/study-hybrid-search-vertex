"""Training job settings."""

from common.config import BaseAppSettings


class TrainSettings(BaseAppSettings):
    wandb_project: str = "bq-first-california-housing"
    wandb_api_key: str = ""  # blank => offline mode
    # LightGBM hyperparameters (shared between regressor + LambdaRank)
    num_leaves: int = 31
    learning_rate: float = 0.05
    feature_fraction: float = 0.9
    bagging_fraction: float = 0.8
    bagging_freq: int = 5
    num_iterations: int = 500
    early_stopping_rounds: int = 30
    # LambdaRank-specific hyperparameters (Phase 3b — unused by cli.py regressor)
    min_data_in_leaf: int = 50
    lambdarank_truncation_level: int = 20
