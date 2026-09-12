from onyx.server.features.build.session.md_images import (
    resolve_local_markdown_image_path,
)

_MD = "outputs/markdown/clinical-initiation-report.md"


def test_resolves_relative_sibling_figure() -> None:
    assert (
        resolve_local_markdown_image_path("figures/competitor_timeline.png", _MD)
        == "outputs/markdown/figures/competitor_timeline.png"
    )


def test_resolves_sandbox_uri() -> None:
    assert (
        resolve_local_markdown_image_path(
            "sandbox://outputs/markdown/figures/competitor_timeline.png", _MD
        )
        == "outputs/markdown/figures/competitor_timeline.png"
    )


def test_resolves_workspace_rooted_path() -> None:
    assert (
        resolve_local_markdown_image_path(
            "outputs/markdown/figures/competitor_timeline.png", _MD
        )
        == "outputs/markdown/figures/competitor_timeline.png"
    )


def test_resolves_dot_relative_path() -> None:
    assert (
        resolve_local_markdown_image_path("./figures/competitor_timeline.png", _MD)
        == "outputs/markdown/figures/competitor_timeline.png"
    )


def test_rejects_http_and_data_urls() -> None:
    assert resolve_local_markdown_image_path("https://example.com/a.png", _MD) is None
    assert resolve_local_markdown_image_path("data:image/png;base64,xx", _MD) is None


def test_rejects_path_that_escapes_workspace() -> None:
    assert resolve_local_markdown_image_path("../../../etc/passwd", _MD) is None


def test_parent_relative_stays_in_workspace() -> None:
    assert (
        resolve_local_markdown_image_path("../figures/plot.png", _MD)
        == "outputs/figures/plot.png"
    )
