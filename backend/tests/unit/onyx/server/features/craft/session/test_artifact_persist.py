from onyx.db.enums import ArtifactType
from onyx.server.features.build.session.artifact_persist import (
    catalog_paths_for_request,
    infer_artifact_type,
    should_auto_promote_output,
    should_skip_output_path,
    workspace_read_path,
)


def test_skip_web_and_vendor_trees() -> None:
    assert should_skip_output_path("web/app/page.tsx")
    assert should_skip_output_path("tools/node_modules/leftpad/index.js")
    assert not should_skip_output_path("report.docx")


def test_catalog_and_workspace_paths() -> None:
    assert workspace_read_path("deck.pptx") == "outputs/deck.pptx"
    assert workspace_read_path("__attachments__/brief.pdf") == "attachments/brief.pdf"
    assert "deck.pptx" in catalog_paths_for_request("outputs/deck.pptx")
    assert "__attachments__/brief.pdf" in catalog_paths_for_request(
        "attachments/brief.pdf"
    )


def test_infer_artifact_type() -> None:
    assert infer_artifact_type("notes.docx") == ArtifactType.DOCX
    assert infer_artifact_type("sheet.xlsx") == ArtifactType.EXCEL
    assert infer_artifact_type("readme.md") == ArtifactType.MARKDOWN


def test_working_control_files_are_not_auto_promoted() -> None:
    assert should_auto_promote_output("markdown/report.md") is True
    assert should_auto_promote_output("deck.pptx") is True
    assert should_auto_promote_output("PLAN.md") is False
    assert should_auto_promote_output("TODO.md") is False
    assert should_auto_promote_output("MEMORY.md") is False
    assert should_auto_promote_output("DONE.json") is False
    assert should_auto_promote_output("plan/PLAN.json") is False
    assert should_auto_promote_output("research/notes.md") is False
