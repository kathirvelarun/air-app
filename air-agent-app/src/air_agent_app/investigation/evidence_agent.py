"""Section 3.2: the shape every evidence agent implements."""

from abc import ABC, abstractmethod

from air_agent_app.models.evidence import Evidence


class BaseEvidenceAgent[RequestT, RawT, NormalizedT](ABC):
    """Collect raw facts, normalize them, then summarize as Evidence.

    Concrete agents own the meaning of "raw" and "normalized" for their
    domain (log lines, metric series, deployment events, ...). This class
    only fixes the order of operations and the boundary that agents return
    observations, never a root cause or a remediation.
    """

    @abstractmethod
    async def collect(self, request: RequestT) -> RawT:
        """Fetch unprocessed data from the underlying tool adapter."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: RawT) -> NormalizedT:
        """Convert raw tool output into typed, comparable records."""
        raise NotImplementedError

    @abstractmethod
    def summarize(self, normalized: NormalizedT, request: RequestT) -> list[Evidence]:
        """Compute deterministic findings and build the Evidence result."""
        raise NotImplementedError

    async def execute(self, request: RequestT) -> list[Evidence]:
        """Run the full collect -> normalize -> summarize pipeline once."""
        raw = await self.collect(request)
        normalized = self.normalize(raw)
        return self.summarize(normalized, request)
