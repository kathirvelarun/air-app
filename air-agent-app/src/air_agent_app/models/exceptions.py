"""Application exceptions callers can handle without knowing the validator."""


class InvalidPlanError(ValueError):
    """The supplied planner output does not satisfy the data contract."""


class InvalidIncidentError(ValueError):
    """The incident cannot be accepted by the planning workflow."""


class ModelCallError(RuntimeError):
    """The model provider failed to complete the planning request."""


class ConfigurationError(ValueError):
    """Required model configuration is missing or invalid."""


class InvalidInvestigationResultError(ValueError):
    """The LLM Investigation Agent's output does not satisfy the data contract."""


class UnknownSourceReferenceError(ValueError):
    """The LLM cited a source reference absent from the supplied evidence."""


class RcaModelCallError(RuntimeError):
    """The model provider failed to complete the RCA investigation request."""


class RcaExecutionError(RuntimeError):
    """The RCA investigation did not produce a usable result after bounded retries.

    This is an execution failure, not a semantic outcome: unlike
    ``INCONCLUSIVE`` (a valid, expected ``InvestigationResult`` when the
    evidence itself is insufficient), this means the model, transport, or
    output contract failed before a result could even be evaluated.
    """
