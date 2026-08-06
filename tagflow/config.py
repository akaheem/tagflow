"""Configuration for TagFlow.

Connection details come from environment variables (matching DataHub's own
conventions) so TagFlow works against the local Quickstart out of the box and
against a secured instance by setting a token.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


# Tag/term names that represent sensitive classifications worth propagating.
# Matched case-insensitively against the tag/term name portion of the URN.
DEFAULT_SENSITIVE_KEYWORDS: List[str] = [
    "pii",
    "sensitive",
    "confidential",
    "gdpr",
    "phi",
    "personal",
    "restricted",
]


@dataclass
class TagFlowConfig:
    """Runtime configuration for a TagFlow run."""

    gms_url: str = field(
        default_factory=lambda: os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")
    )
    gms_token: str = field(
        default_factory=lambda: os.getenv("DATAHUB_GMS_TOKEN", "")
    )

    # How many hops downstream to propagate classifications.
    max_hops: int = 3

    # Only propagate tags/terms whose name matches one of these keywords.
    # Set to an empty list to propagate *all* upstream classifications.
    sensitive_keywords: List[str] = field(
        default_factory=lambda: list(DEFAULT_SENSITIVE_KEYWORDS)
    )

    # When True, compute and report changes but never write to DataHub.
    dry_run: bool = True

    def is_sensitive(self, name: str) -> bool:
        """Return True if a tag/term name matches the sensitivity policy."""
        if not self.sensitive_keywords:
            return True
        lowered = name.lower()
        return any(keyword in lowered for keyword in self.sensitive_keywords)
