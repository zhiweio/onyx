from pathlib import Path
from typing import cast

import puremagic
from pydantic import BaseModel

from onyx.utils.logger import setup_logger

logger = setup_logger()


class FileWithMimeType(BaseModel):
    data: bytes
    mime_type: str


class OnyxStaticFileManager:
    """Retrieve static resources with this class. Currently, these should all be located
    in the static directory ... e.g. static/images/logo.png"""

    @staticmethod
    def get_static(filename: str) -> FileWithMimeType | None:
        # static/ lives at the backend root. Resolve relative to CWD first
        # (the container layout), then relative to the backend root so the
        # lookup also works when the CWD is elsewhere (e.g. pytest from the
        # repo root).
        candidates = [
            Path(filename),
            Path(__file__).resolve().parents[2] / filename,
        ]
        for candidate in candidates:
            try:
                mime_type: str = "application/octet-stream"
                with open(candidate, "rb") as f:
                    file_content = f.read()
                    matches = puremagic.magic_string(file_content)
                    if matches:
                        mime_type = cast(str, matches[0].mime_type)
                return FileWithMimeType(data=file_content, mime_type=mime_type)
            except (OSError, FileNotFoundError, PermissionError) as e:
                logger.error("Failed to read file %s: %s", candidate, e)
            except Exception as e:
                logger.error("Unexpected exception reading file %s: %s", candidate, e)

        return None
