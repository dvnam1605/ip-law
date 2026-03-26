from abc import ABC, abstractmethod
from typing import Dict
from backend.core.router_constants import (
    RouteType,
    VERDICT_PATTERNS,
    LEGAL_PATTERNS,
    TRADEMARK_PATTERNS,
    ADVISORY_COMPILED
)

class RoutingStrategy(ABC):
    @abstractmethod
    def score(self, query: str) -> float:
        """Returns a score for the given query based on the strategy's logic."""
        pass

class KeywordRoutingStrategy(RoutingStrategy):
    def __init__(self, patterns):
        self.patterns = patterns

    def score(self, query: str) -> float:
        return sum(1 for p in self.patterns if p.search(query))

class AdvisoryRoutingStrategy(RoutingStrategy):
    def __init__(self, patterns):
        self.patterns = patterns

    def score(self, query: str) -> float:
        return 1.0 if any(p.search(query) for p in self.patterns) else 0.0

def classify_query_with_strategies(query: str, strategies: Dict[str, RoutingStrategy]) -> RouteType:
    q = query.strip()
    if not q:
        return 'legal'

    verdict_score = strategies['verdict'].score(q)
    legal_score = strategies['legal'].score(q)
    trademark_score = strategies['trademark'].score(q)
    advisory_hit = strategies['advisory'].score(q) > 0

    # 1. Trademark intent takes priority when specific trademark keywords are present
    # If there's a clear trademark intent, we prefer trademark route unless there's a 
    # MUCH stronger verdict/legal signal.
    if trademark_score >= 2:
        return 'trademark'
    if trademark_score >= 1:
        if verdict_score <= 2 and legal_score <= 1:
            return 'trademark'

    # 2. Advisory intent + some verdict signals -> Combined
    if advisory_hit and verdict_score >= 1:
        return 'combined'

    # 3. High overlap -> Combined
    if verdict_score >= 2 and legal_score >= 2:
        return 'combined'

    # 4. Specific high signals
    if verdict_score > legal_score and verdict_score >= 2:
        return 'verdict'
    
    if legal_score > verdict_score and legal_score >= 1:
        return 'legal'

    # 5. Default fallback to combined if any verdict signal, else legal
    if verdict_score >= 1:
        return 'combined'
    
    return 'legal'

DEFAULT_STRATEGIES = {
    'verdict': KeywordRoutingStrategy(VERDICT_PATTERNS),
    'legal': KeywordRoutingStrategy(LEGAL_PATTERNS),
    'trademark': KeywordRoutingStrategy(TRADEMARK_PATTERNS),
    'advisory': AdvisoryRoutingStrategy(ADVISORY_COMPILED)
}
