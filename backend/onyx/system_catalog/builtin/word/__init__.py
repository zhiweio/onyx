"""Official Word report-template generators.

Documents are generated in Python so diffs stay reviewable and placeholders
cannot drift from the schema that sync attaches.
"""

from onyx.system_catalog.builtin.word.generate import generate_official_docx

__all__ = ["generate_official_docx"]
