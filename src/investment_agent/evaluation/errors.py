from enum import StrEnum


class ErrorTaxonomy(StrEnum):
    """Standardized error taxonomy for agent reality monitoring and self-correction."""

    DATA_ERROR = "DATA_ERROR"
    SOURCE_ERROR = "SOURCE_ERROR"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    REASONING_ERROR = "REASONING_ERROR"
    ASSUMPTION_ERROR = "ASSUMPTION_ERROR"
    TIMING_ERROR = "TIMING_ERROR"
    THESIS_ERROR = "THESIS_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    EXTERNAL_EVENT = "EXTERNAL_EVENT"
