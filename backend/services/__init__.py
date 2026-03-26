from backend.services.legal import QueryService, get_query_service
from backend.services.verdict import VerdictService, get_verdict_service
from backend.services.trademark import TrademarkService, get_trademark_service

__all__ = [
    "QueryService",
    "VerdictService",
    "TrademarkService",
    "get_query_service",
    "get_verdict_service",
    "get_trademark_service",
]
