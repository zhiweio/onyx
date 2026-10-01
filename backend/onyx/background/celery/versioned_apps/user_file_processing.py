"""Factory stub for running the user file processing Celery worker."""

from celery import Celery

from onyx.utils.variable_functionality import (
    fetch_versioned_implementation,
)

app: Celery = fetch_versioned_implementation(
    "onyx.background.celery.apps.user_file_processing",
    "celery_app",
)
