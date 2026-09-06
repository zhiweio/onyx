import json
from collections.abc import Callable

from onyx.context.search.models import InferenceSection
from onyx.context.search.utils import sandbox_filename_for_document
from onyx.utils.logger import setup_logger

logger = setup_logger()

_OUTPUT_TRUNCATED_FOOTER = "\n... [output truncated, {omitted} characters omitted]"


def truncate_output(output: str, max_length: int, label: str = "output") -> str:
    """Truncate to ``max_length`` and append a footer noting how many chars were elided. ``label`` is only used in the debug log."""
    truncated = output[:max_length]
    if len(output) > max_length:
        truncated += _OUTPUT_TRUNCATED_FOOTER.format(omitted=len(output) - max_length)
        logger.debug("Truncated %s: %s", label, truncated)
    return truncated


def fit_text_to_token_budget(
    text: str,
    token_counter: Callable[[str], int],
    max_tokens: int,
) -> str:
    """Keep as much of ``text`` as fits in ``max_tokens``, with a truncation footer.

    The tool still produced the full result. This only cuts what is written
    into conversation history so one MCP answer cannot overflow the window.
    """
    if max_tokens <= 0:
        return _OUTPUT_TRUNCATED_FOOTER.format(omitted=len(text)).lstrip()
    if token_counter(text) <= max_tokens:
        return text

    lo = 0
    hi = len(text)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        omitted = len(text) - mid
        candidate = text[:mid] + _OUTPUT_TRUNCATED_FOOTER.format(omitted=omitted)
        if token_counter(candidate) <= max_tokens:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    if best:
        return best
    return _OUTPUT_TRUNCATED_FOOTER.format(omitted=len(text)).lstrip()


FILE_ASSOCIATED_GUIDANCE = (
    "Only a short excerpt from this document is shown below. The complete "
    'file is available in the sandbox as "{filename}" — prefer the Python '
    "code interpreter to read, parse, or analyze it\n\n"
    "Excerpt: {content}"
)


def convert_inference_sections_to_llm_string(
    top_sections: list[InferenceSection],
    citation_start: int = 1,
    limit: int | None = None,
    include_source_type: bool = True,
    include_link: bool = False,
    include_document_id: bool = False,
    note: str | None = None,
) -> tuple[str, dict[int, str]]:
    """Convert InferenceSection objects to a JSON string for LLM.

    Returns a JSON string with document results and a citation mapping.
    """
    # Apply limit if specified
    if limit is not None:
        top_sections = top_sections[:limit]

    # Group sections by document_id to assign same citation_id to sections from same document
    document_id_to_citation_id: dict[str, int] = {}
    citation_mapping: dict[int, str] = {}
    current_citation_id = citation_start

    # First pass: assign citation_ids to unique document_ids
    for section in top_sections:
        document_id = section.center_chunk.document_id
        if document_id not in document_id_to_citation_id:
            document_id_to_citation_id[document_id] = current_citation_id
            citation_mapping[current_citation_id] = document_id
            current_citation_id += 1

    # Second pass: build results with citation_ids assigned per document
    results = []

    for section in top_sections:
        chunk = section.center_chunk
        document_id = chunk.document_id
        citation_id = document_id_to_citation_id[document_id]

        # Combine primary and secondary owners for authors
        authors = None
        if chunk.primary_owners or chunk.secondary_owners:
            authors = []
            if chunk.primary_owners:
                authors.extend(chunk.primary_owners)
            if chunk.secondary_owners:
                authors.extend(chunk.secondary_owners)

        # Format updated_at as ISO string if available
        updated_at_str = None
        if chunk.updated_at:
            updated_at_str = chunk.updated_at.isoformat()

        # Build result dictionary in desired order, only including non-None/empty fields
        result = {
            "document": citation_id,
            "title": chunk.semantic_identifier,
        }
        if updated_at_str is not None:
            result["updated_at"] = updated_at_str
        if authors is not None:
            result["authors"] = authors
        if include_source_type:
            result["source_type"] = chunk.source_type.value
        if include_link:
            # Get the first link from the center chunk's source_links dict
            link = None
            if chunk.source_links:
                # source_links is dict[int, str], get the first value
                link = next(iter(chunk.source_links.values()), None)
            if link:
                result["url"] = link
        if include_document_id:
            result["document_identifier"] = chunk.document_id
        if chunk.file_id is not None:
            filename = sandbox_filename_for_document(
                chunk.semantic_identifier, chunk.file_id
            )
            result["file_name"] = filename

            result["content"] = FILE_ASSOCIATED_GUIDANCE.format(
                filename=filename, content=chunk.content
            )
        else:
            result["content"] = section.combined_content
        if chunk.metadata:
            result["metadata"] = json.dumps(chunk.metadata, ensure_ascii=False)
        results.append(result)

    payload: dict[str, object] = {}
    payload["results"] = results
    if note:
        payload["note"] = note

    return (
        json.dumps(payload, indent=2, ensure_ascii=False),
        citation_mapping,
    )
