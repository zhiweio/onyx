"""Interrupt kind surfaces must stay aligned across graph and channels."""

from typing import get_args

from onyx.server.features.build.jobs.channels import InterruptKind
from onyx.server.features.build.jobs.graph import HitlKind


def test_node_declarable_hitl_is_subset_of_interrupt_kinds() -> None:
    """HitlKind minus `none` must equal InterruptKind minus the host-only
    `clarify`, so a node can never declare an interrupt the state cannot hold."""
    assert set(get_args(HitlKind)) - {"none"} == set(get_args(InterruptKind)) - {
        "clarify"
    }
