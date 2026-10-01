"""Factory stub for running celery worker / celery beat."""

from celery import Celery

from onyx.utils.variable_functionality import (
    fetch_versioned_implementation,
)

app: Celery = fetch_versioned_implementation(
    "onyx.background.celery.apps.docfetching",
    "celery_app",
)
