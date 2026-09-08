"""Duplicate protection (workflow sections 9, 15, 20): before adding a new
Market Signal, Competitor, Audience Problem, or Campaign, check it against
what's already stored so the workbook accumulates knowledge instead of
restating it with different wording each week.

Same token-Jaccard approach already proven in tools/research_vital_sync.py's
DedupPool — kept deliberately simple and dependency-free (no embeddings, no
paid API) since "same audience + same problem + same angle" duplication is
usually obvious at the word-overlap level.
"""

import re

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "for", "with", "and", "or", "but", "not",
    "this", "that", "it", "its", "you", "your", "i", "my", "we", "our",
    "do", "does", "did", "can", "should", "how", "what", "why", "vs",
}


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).strip()


def tokenize(text: str) -> set:
    return {t for t in normalize(text).split() if t and t not in STOPWORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class DuplicatePool:
    """Holds tokenized fingerprints of existing records plus a similarity
    threshold, and answers "does this new record already exist?"."""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.records = []  # list of (tokens, source_dict)

    def add(self, key_text: str, source: dict):
        self.records.append((tokenize(key_text), source))

    def find_duplicate(self, key_text: str):
        """Returns the matching source dict if a near-duplicate exists,
        else None."""
        tokens = tokenize(key_text)
        best_score, best_source = 0.0, None
        for existing_tokens, source in self.records:
            score = jaccard(tokens, existing_tokens)
            if score > best_score:
                best_score, best_source = score, source
        if best_score >= self.threshold:
            return best_source
        return None


def campaign_key(campaign: dict) -> str:
    """Concatenates the fields that define a campaign's *concept* (not its
    wording) — audience, problem, angle, message, feature — so "Stay
    Consistent" and "Consistency Wins" collapse to the same fingerprint."""
    parts = [
        campaign.get("Audience Segment", ""),
        campaign.get("Audience Problem", ""),
        campaign.get("Marketing Angle", ""),
        campaign.get("Core Message", ""),
        campaign.get("Product Feature", ""),
    ]
    return " ".join(str(p) for p in parts if p)


def signal_key(signal: dict) -> str:
    parts = [signal.get("Topic", ""), signal.get("Search / Social Query", "")]
    return " ".join(str(p) for p in parts if p)


def audience_problem_key(problem: dict) -> str:
    parts = [
        problem.get("Audience Segment", ""),
        problem.get("Problem Cluster", ""),
        problem.get("Audience Problem", ""),
    ]
    return " ".join(str(p) for p in parts if p)
