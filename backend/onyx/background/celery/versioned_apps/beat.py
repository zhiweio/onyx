"""Factory stub for running celery worker / celery beat."""

from celery import Celery

from onyx.background.celery.apps.beat import celery_app

app: Celery = celery_app
