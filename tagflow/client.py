"""DataHub connection wrapper for TagFlow.

Centralizes construction of the DataHub SDK clients so the rest of the codebase
never touches connection details directly. We expose both:

  * the high-level ``DataHubClient`` (used for multi-hop lineage traversal), and
  * the lower-level ``DataHubGraph`` client (used for aspect-level tag/term
    reads and metadata writes).
"""

from __future__ import annotations

from tagflow.config import TagFlowConfig


class TagFlowClient:
    """Thin wrapper holding the DataHub SDK clients TagFlow needs."""

    def __init__(self, config: TagFlowConfig):
        self.config = config
        self._graph = None
        self._sdk = None

    @property
    def graph(self):
        """Lazily construct the low-level DataHubGraph client."""
        if self._graph is None:
            from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

            self._graph = DataHubGraph(
                DatahubClientConfig(
                    server=self.config.gms_url,
                    token=self.config.gms_token or None,
                )
            )
        return self._graph

    @property
    def sdk(self):
        """Lazily construct the high-level DataHubClient (lineage traversal)."""
        if self._sdk is None:
            from datahub.sdk.main_client import DataHubClient

            self._sdk = DataHubClient(
                server=self.config.gms_url,
                token=self.config.gms_token or None,
            )
        return self._sdk

    def check_connection(self) -> bool:
        """Verify we can reach the DataHub instance. Raises on failure."""
        # get_config() hits the GMS /config endpoint — a cheap liveness probe.
        self.graph.get_config()
        return True
