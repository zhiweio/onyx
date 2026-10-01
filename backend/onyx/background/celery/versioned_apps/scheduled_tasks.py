"""Factory stub for running the Craft scheduled-tasks Celery worker."""

from celery import Celery

from onyx.utils.variable_functionality import (
    fetch_versioned_implementation,
)

app: Celery = fetch_versioned_implementation(
    "onyx.background.celery.apps.scheduled_tasks",
    "celery_app",
)
