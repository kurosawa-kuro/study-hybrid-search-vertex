terraform {
  backend "gcs" {
    bucket = "mlops-dev-a-tfstate"
    prefix = "bq-first"
  }
}
