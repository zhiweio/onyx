from types import SimpleNamespace

from onyx.db.craft_project import is_implicit_untitled_project
from onyx.server.features.build.jobs import kernel as job_kernel


def test_is_implicit_untitled_project() -> None:
    assert is_implicit_untitled_project(
        SimpleNamespace(
            name="Untitled project",
            instructions=None,
            description="",
        )
    )
    assert not is_implicit_untitled_project(
        SimpleNamespace(name="Tax pack", instructions=None, description="")
    )
    assert not is_implicit_untitled_project(
        SimpleNamespace(
            name="Untitled project",
            instructions="Be brief.",
            description="",
        )
    )


def test_spawn_lanes_does_not_create_a_project() -> None:
    import inspect

    source = inspect.getsource(job_kernel._spawn_lanes)
    assert "create_project" not in source
