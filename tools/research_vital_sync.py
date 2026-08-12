"""Vital Sync — Workflow 00: Search Intelligence Engine

Discovers real-world search demand around Fitness / Nutrition / Recovery and
appends scored, deduplicated opportunities to the EXISTING Search Bank tab
of the Vital Sync Content Engine sheet. This workflow sits BEFORE Workflow
01 (Script Factory) and does research only — it never generates scripts,
never touches Content Pipeline, and never marks a row "Used" (that belongs
to Workflow 01).

Research sources (see SOURCE INTEGRITY below — never fabricated):
  - Google Autocomplete (suggestqueries.google.com, no key needed) — real.
  - YouTube Suggest (same host, client=youtube) — real.
  - Derived Search Intent — deterministic AnswerThePublic-style template
    expansion (WHY/HOW/WHAT/CAN/SHOULD/DOES/IS/VS/... x seed topics), run
    entirely offline. Honestly labeled as derived, never claimed to come
    from a platform.
  - Reddit, Google Trends, and Google People-Also-Ask are NOT implemented:
    Reddit's public JSON search is blocked from this environment (403),
    and Trends/PAA have no reliable key-free API short of scraping SERP
    HTML (fragile, ToS-risky). These are reported as unavailable sources
    in every run's summary, never silently skipped.

SOURCE INTEGRITY: every accepted row's Source column reflects exactly where
it came from. Trend Signal is "Unknown" unless a source genuinely supports
Rising/Stable/Declining (in this build, none do — that's an honest gap, not
a bug). Search Demand / Audience Relevance / Content Potential / Competition
are 1-10 relative scores computed from a documented, deterministic formula
below — never a fabricated search-volume number or trend percentage.

Search Bank column plan (see workflows/00_search_intelligence.md for the
full rationale): existing columns are reused wherever they already serve
the same purpose so Workflow 01 keeps working unmodified —
  - "Category" IS this workflow's "Primary Pillar" (not renamed: Workflow
    01's build_prompt() reads "Category" directly).
  - "Search Score" / "Trend Score" are populated for every new row because
    Workflow 01's select_topics() ranks unused rows by
    int(Search Score) + int(Trend Score); leaving them blank would sink
    every new opportunity to the bottom of that ranking.
    Search Score = round(Opportunity Score x 10); Trend Score =
    round(Search Demand x 10) — both are explicitly-documented ranking
    proxies on the existing 0-100 scale, never presented as real trend %.
  - "Difficulty" / "Follower Potential" are kept and populated from the
    Competition / Content Potential bands so they stay meaningful.
  - 17 new columns (Search ID, Date Found, Seed Topic, Audience Problem,
    Subcategory, Audience Level, Source, Source Detail, Trend Signal,
    Search Demand, Audience Relevance, Content Potential, Competition,
    Opportunity Score, Priority, Date Used, Notes) are appended after the
    existing 10 via sheets_io.ensure_headers() — additive only, nothing
    existing is deleted, renamed, or reordered.

This tool makes ZERO paid API calls (no OpenAI) — safe to re-run freely.

Usage:
    python tools/research_vital_sync.py --dry-run --batch-size 30
    python tools/research_vital_sync.py --live --batch-size 30 --no-email
    python tools/research_vital_sync.py --live --trigger scheduled
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

import gmail_send
import sheets_io

WORKFLOW_NAME = "Vital Sync Search Intelligence Engine"

SEARCH_BANK_TAB = "Search Bank"
CONTENT_PIPELINE_TAB = "Content Pipeline"
AUTOMATION_LOGS_TAB = "Automation Logs"
AUTOMATION_LOGS_HEADERS = ["Date", "Workflow", "Success", "Time", "Errors"]

STATUS_UNUSED = "Unused"

# Overlap-prevention: mirrors the started/completed pattern already used by
# Workflows 01/02 (paired markers in Automation Logs, no lock files — the
# sheet is the lock). A run whose "started" marker is older than this with
# no matching "completed"/"skipped" marker is treated as crashed, not
# active. This tool has no "Processing" status to self-heal (it only ever
# appends new rows, never reserves existing ones), so unlike Workflow 01
# there's nothing to reclaim — the lock alone is enough. A short timeout is
# appropriate since a normal run finishes in a couple of minutes.
STALE_RUN_TIMEOUT_MINUTES = 30

# Existing Search Bank headers, left exactly as-is (order and names).
SEARCH_BANK_LEGACY_COLUMNS = [
    "Search Query", "Topic", "Category", "Search Intent", "Difficulty",
    "Search Score", "Trend Score", "Follower Potential", "Product Opportunity",
    "Status",
]
# New columns this workflow adds (appended after the legacy ones).
SEARCH_BANK_NEW_COLUMNS = [
    "Search ID", "Date Found", "Seed Topic", "Audience Problem", "Subcategory",
    "Audience Level", "Source", "Source Detail", "Trend Signal", "Search Demand",
    "Audience Relevance", "Content Potential", "Competition", "Opportunity Score",
    "Priority", "Date Used", "Notes",
]
SEARCH_BANK_REQUIRED_HEADERS = SEARCH_BANK_LEGACY_COLUMNS + SEARCH_BANK_NEW_COLUMNS

# ---------------------------------------------------------------------------
# Seed library (section 22) — configurable, not a hard limit. New seeds can
# be added here as the niche evolves; the research engine also surfaces
# "candidate new seeds" in its summary for a human to review and add later.
# ---------------------------------------------------------------------------
SEED_TOPICS = {
    "Fitness": [
        "Muscle Growth", "Strength", "Progressive Overload", "Workout Programming",
        "Exercise Form", "Fat Loss", "Cardio", "Calisthenics",
    ],
    "Nutrition": [
        "Protein", "Carbohydrates", "Hydration", "Creatine", "Calories",
        "Meal Timing", "Sports Nutrition",
    ],
    "Recovery": [
        "Sleep", "DOMS", "Rest Days", "Active Recovery", "Mobility",
        "Fatigue", "Deloading",
    ],
}

SUBCATEGORY_MAP = {
    "Muscle Growth": "Muscle Growth", "Strength": "Strength",
    "Progressive Overload": "Programming", "Workout Programming": "Programming",
    "Exercise Form": "Exercise Form", "Fat Loss": "Fat Loss", "Cardio": "Cardio",
    "Calisthenics": "Calisthenics",
    "Protein": "Protein", "Carbohydrates": "Carbohydrates", "Hydration": "Hydration",
    "Creatine": "Supplements", "Calories": "Calories", "Meal Timing": "Meal Timing",
    "Sports Nutrition": "Sports Nutrition",
    "Sleep": "Sleep", "DOMS": "DOMS", "Rest Days": "Rest Days",
    "Active Recovery": "Active Recovery", "Mobility": "Mobility",
    "Fatigue": "Fatigue", "Deloading": "Deloading",
}

# Seeds considered broad/"head" terms for the Competition heuristic below.
HIGH_COMPETITION_SEEDS = {
    "Muscle Growth", "Strength", "Protein", "Sleep", "Fat Loss", "Cardio", "Calories",
}

# AnswerThePublic-style expansion families (section 11). "prefix" families are
# sent to autocomplete as "{word} {seed}"; "suffix" families as "{seed} {word}".
EXPANSION_PREFIXES = [
    "why", "how much", "how often", "should i", "does", "is", "best", "can i",
]
EXPANSION_SUFFIXES = ["vs", "without", "with", "before training", "after training"]

# A handful of concrete, on-brand object words per seed used only for the
# offline "Derived Search Intent" template expansion (section 11), grounded
# directly in the example questions the brand spec itself gives for each
# pillar (sections 8-10) — not invented.
DERIVED_MODIFIERS = {
    "Muscle Growth": ["for beginners", "without weights", "with high reps", "plateau"],
    "Strength": ["without adding size", "vs hypertrophy", "plateau"],
    "Progressive Overload": ["for beginners", "without more weight"],
    "Workout Programming": ["for beginners", "for muscle gain"],
    "Exercise Form": ["mistakes", "for squats", "for deadlifts"],
    "Fat Loss": ["without losing muscle", "vs muscle gain", "mistakes"],
    "Cardio": ["vs weights", "for fat loss", "mistakes"],
    "Calisthenics": ["for beginners", "vs weights"],
    "Protein": ["per meal", "per day", "without meat", "timing"],
    "Carbohydrates": ["before training", "at night", "for muscle gain"],
    "Hydration": ["for performance", "electrolytes"],
    "Creatine": ["timing", "side effects", "loading phase"],
    "Calories": ["for muscle gain", "for fat loss", "deficit"],
    "Meal Timing": ["before training", "after training"],
    "Sports Nutrition": ["for beginners", "myths"],
    "Sleep": ["and muscle growth", "quality", "mistakes"],
    "DOMS": ["how long", "vs injury"],
    "Rest Days": ["how many", "vs active recovery"],
    "Active Recovery": ["ideas", "vs rest days"],
    "Mobility": ["vs stretching", "before training"],
    "Fatigue": ["vs overtraining", "signs"],
    "Deloading": ["how often", "signs you need one"],
}

BANNED_PATTERNS = [
    r"\bsteroid", r"\banorexi", r"\bbulimi", r"\boverdose\b", r"\bsuicid",
    r"\bdiagnos", r"\bcancer\b", r"\bsurgery\b", r"\bprescription\b",
    r"\bdebt\b", r"\bcrypto\b", r"\bstock market\b", r"\bpassive income\b",
    r"\bget rich\b", r"\bdating\b", r"\brelationship advice\b", r"\bdivorce\b",
    r"\bextreme fast", r"\bzero calorie\b", r"\bstarvation\b",
    # Clinical-population / disease-specific content — leave this to doctors,
    # not a general fitness/nutrition/recovery brand (found via QA review:
    # "why is meal timing important for clients with diabetes" slipped past
    # the original filter and had to be corrected post-hoc, see workflow doc).
    r"\bdiabet", r"\bpcos\b", r"\bthyroid\b", r"\bhigh blood pressure\b",
    r"\bpregnan", r"\bclients? with\b",
]

# Autocomplete/YouTube suggest endpoints return a lot of unrelated pop-culture
# noise for fitness-adjacent seed words (e.g. "muscle growth" is also a
# well-known anime/manga trope). Filtered out as off-niche, not banned.
JUNK_PATTERNS = [
    r"\banime\b", r"\bmanga\b", r"\bcomic\b", r"\bcosplay\b", r"\bfanfic",
    r"\bwiki\b", r"\breddit\b", r"\bquora\b", r"\btumblr\b", r"\bmovie\b",
    r"\btv show\b", r"\bgame\b", r"\bmeme\b", r"\bgif\b", r"\bcostume\b",
    r"\blyrics\b", r"\bsong\b", r"\bplush\b", r"\btoy\b", r"\bcoloring page\b",
    r"\bmarvel\b", r"\bdc comics\b", r"\bcast\b", r"\bepisode\b",
    r"\bhero academia\b", r"\bstories\b", r"\bpokemon\b", r"\bhentai\b",
    r"\bnsfw\b", r"\borg\b", r"\bgrammar\b", r"\bpdf\b", r"\bworksheet\b",
    r"\bworkbook\b", r"\banswers\b", r"\bdownload\b", r"\benglish exercise\b",
    r"\bcoaches? make\b", r"\bsalary\b", r"\bhow to become a\b", r"\bcertification\b",
    r"\bdegree\b", r"\bcareer\b",
]

STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "to", "for", "of", "in", "on",
    "and", "or", "my", "i", "you", "your", "i'm", "im", "me", "at", "it", "be",
    "so", "if", "but", "than", "that", "this", "there",
}

CORE_BRAND_TERMS = {
    "training", "nutrition", "recovery", "consistency", "performance", "workout",
    "exercise", "gym", "diet", "macro", "macros", "supplement", "supplements",
    "program", "programming", "plateau", "technique", "form", "habit", "routine",
}

PRODUCT_KEYWORDS = {"track", "tracking", "program", "programming", "plan", "planning",
                     "consistency", "system", "routine", "app"}


# ---------------------------------------------------------------------------
# Research sources
# ---------------------------------------------------------------------------

def fetch_suggest(query: str, client: str, timeout: float = 6.0):
    """Real, key-free Google/YouTube suggest endpoint. Returns a list of
    suggestion strings, or None if the source could not be reached (caller
    logs the failure honestly — never fabricates a replacement)."""
    try:
        resp = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": client, "q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        text = resp.text.strip()
        if text.startswith("window.google.ac.h("):
            text = text[len("window.google.ac.h("):-1]
        data = json.loads(text)
        out = []
        for s in data[1]:
            out.append(s[0] if isinstance(s, list) else s)
        return out
    except Exception:
        return None


def fetch_reddit(query: str, timeout: float = 6.0):
    """Reddit's public search JSON endpoint. Confirmed blocked (403) from
    this environment during development — kept here so it activates
    automatically if reachable from wherever this actually runs, but never
    assumed to work."""
    try:
        resp = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "limit": 8, "sort": "relevance"},
            headers={"User-Agent": "vital-sync-research/1.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return [c["data"]["title"] for c in data.get("data", {}).get("children", [])]
    except Exception:
        return None


def check_source_availability():
    """One connectivity probe per source, done once per run. Returns
    (available_sources, unavailable_sources_with_reason)."""
    available, unavailable = [], []

    if fetch_suggest("protein", "firefox") is not None:
        available.append("Google Autocomplete")
    else:
        unavailable.append(("Google Autocomplete", "endpoint unreachable or errored"))

    if fetch_suggest("protein", "youtube") is not None:
        available.append("YouTube")
    else:
        unavailable.append(("YouTube", "endpoint unreachable or errored"))

    if fetch_reddit("protein timing") is not None:
        available.append("Reddit")
    else:
        unavailable.append(("Reddit", "blocked (HTTP 403) or unreachable from this network"))

    unavailable.append(("Google Trends", "no key-free reliable API available in this environment"))
    unavailable.append(("Google People Also Ask", "requires SERP scraping — not implemented (fragile/ToS-risky)"))
    unavailable.append(("Google Related Searches", "requires SERP scraping — not implemented (fragile/ToS-risky)"))

    return available, unavailable


def derived_expansion_queries(seed: str):
    """Deterministic, offline AnswerThePublic-style template expansion
    (section 11), grounded in the brand's own seed vocabulary. Never
    claimed to come from any external platform."""
    seed_l = seed.lower()
    queries = []
    for modifier in DERIVED_MODIFIERS.get(seed, []):
        queries.append(f"{seed_l} {modifier}")
    # A few generic, always-applicable template forms.
    queries += [
        f"why {seed_l} isn't working",
        f"how much {seed_l} do i need",
        f"best {seed_l} tips",
        f"common {seed_l} mistakes",
    ]
    return queries


# ---------------------------------------------------------------------------
# Normalization / dedup
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> set:
    return {t for t in normalize(text).split() if t and t not in STOPWORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class DedupPool:
    """Tracks normalized queries + token sets seen so far (existing Search
    Bank rows, relevant Content Pipeline topics, and everything accepted
    earlier in this same run) so exact and semantic duplicates are caught
    before anything is written."""

    def __init__(self):
        self.exact = set()
        self.token_sets = []

    def add(self, text: str):
        norm = normalize(text)
        if not norm:
            return
        self.exact.add(norm)
        self.token_sets.append(tokenize(text))

    def is_duplicate(self, text: str, threshold: float = 0.6) -> str:
        norm = normalize(text)
        if not norm:
            return "empty"
        if norm in self.exact:
            return "exact"
        tokens = tokenize(text)
        for existing in self.token_sets:
            if jaccard(tokens, existing) >= threshold:
                return "semantic"
        return ""


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

INTENT_RULES = [
    (r"^(common )?mistakes\b", "Mistake"),
    (r"^signs of\b", "Signs"),
    (r"\bmyths?\b", "Myth"),
    (r"\bvs\b|\bversus\b", "Comparison"),
    (r"^best\b", "Recommendation"),
    (r"^how (much|many)\b", "Frequency"),
    (r"^how often\b", "Frequency"),
    (r"^how (long|fast)\b", "Timing"),
    (r"\bbefore training\b|\bafter training\b", "Timing"),
    (r"^how\b", "How-To"),
    (r"^why\b", "Troubleshooting"),
    (r"^what happens if\b", "Troubleshooting"),
    (r"^what causes\b", "Problem"),
    (r"^what\b", "Education"),
    (r"^can\b", "Recommendation"),
    (r"^should\b", "Recommendation"),
    (r"^does\b", "Myth"),
    (r"^is\b", "Comparison"),
    (r"\bwithout\b|\bwith\b", "How-To"),
]


def classify_intent(query: str) -> str:
    q = normalize(query)
    for pattern, intent in INTENT_RULES:
        if re.search(pattern, q):
            return intent
    return "Question"


def classify_audience_level(query: str) -> str:
    q = normalize(query)
    if re.search(r"\bbeginner|\bstart(ing)?\b|\bnew to\b", q):
        return "Beginner"
    if re.search(r"\bplateau|\badvanced|\boptimi[sz]e|\bmaximi[sz]e\b", q):
        return "Advanced"
    if re.search(r"\bintermediate\b", q):
        return "Intermediate"
    return "General"


def is_off_niche_or_unsafe(query: str) -> str:
    """Returns a rejection reason, or '' if the query passes."""
    q = normalize(query)
    if len(q.split()) < 2:
        return "too short / meaningless"
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, q):
            return f"banned topic pattern ({pattern})"
    for pattern in JUNK_PATTERNS:
        if re.search(pattern, q):
            return f"off-niche pop-culture noise ({pattern})"
    return ""


def build_topic_label(query: str, seed: str) -> str:
    """A short Title Case label, preserving the query's original word order
    (tokenize() returns an unordered set — deliberately not used here, or
    the label comes out scrambled)."""
    words = normalize(query).split()
    tokens = [w for w in words if w not in STOPWORDS and w not in {"training", "workout"}]
    if not tokens:
        return seed
    label = " ".join(tokens[:6]).title()
    return label if len(label) > 3 else seed


# ---------------------------------------------------------------------------
# Scoring (section 15) — transparent, deterministic, no fabricated volume.
# ---------------------------------------------------------------------------

def _pillar_glossary_tokens(pillar: str) -> set:
    toks = set()
    for seed in SEED_TOPICS[pillar]:
        toks |= set(normalize(seed).split())
        toks |= set(normalize(SUBCATEGORY_MAP.get(seed, seed)).split())
    return toks


PILLAR_TOKENS = {p: _pillar_glossary_tokens(p) for p in SEED_TOPICS}


def score_audience_relevance(query: str, pillar: str) -> int:
    """Baseline reflects how clearly on-topic for its own pillar a query is;
    a bonus rewards queries that also connect to another pillar or a core
    brand term, since Vital Sync's actual positioning is training + nutrition
    + recovery working together. Keeps scores spread out instead of every
    on-topic query trivially maxing out at 10."""
    tokens = tokenize(query)
    own_matches = len(tokens & PILLAR_TOKENS[pillar])
    other_tokens = set().union(*(t for p, t in PILLAR_TOKENS.items() if p != pillar))
    cross_matches = len(tokens & other_tokens)
    brand_bonus = 1 if tokens & CORE_BRAND_TERMS else 0
    score = 5 + min(2, own_matches) + min(2, cross_matches) + brand_bonus
    return max(1, min(10, score))


def score_content_potential(query: str) -> int:
    words = normalize(query).split()
    score = 5
    if classify_intent(query) != "Question":
        score += 2
    if re.search(r"\d", query) or re.search(r"\b(daily|weekly|per day|per week|per meal)\b", normalize(query)):
        score += 1
    if 4 <= len(words) <= 10:
        score += 1
    if len(words) < 3:
        score -= 2
    return max(1, min(10, score))


def score_competition(query: str, seed: str) -> int:
    words = normalize(query).split()
    score = 5
    if seed in HIGH_COMPETITION_SEEDS:
        score += 1
    if len(words) <= 4:
        score += 2
    if len(words) >= 7:
        score -= 2
    return max(1, min(10, score))


def score_search_demand(source: str, hit_count: int, best_rank) -> int:
    if source in ("Google Autocomplete", "YouTube"):
        score = 6 + min(2, max(0, hit_count - 1))
        if best_rank is not None and best_rank <= 2:
            score += 1
        return max(1, min(9, score))  # capped below 10 — no real volume data to justify a max score
    return 4  # Derived Search Intent: no external evidence, kept modest


def opportunity_score(relevance, potential, demand, competition) -> float:
    advantage = 11 - competition
    return round(0.35 * relevance + 0.30 * potential + 0.25 * demand + 0.10 * advantage, 1)


def assign_priorities_by_rank(items: list) -> None:
    """Sets item['priority'] in place, ranked within the accepted batch
    rather than against a fixed absolute score cutoff. A fixed cutoff
    collapses here because harvesting already selects only the strongest
    scorers out of hundreds of raw candidates per pillar — every accepted
    item would clear a modest absolute bar, which is exactly what section
    16 warns against ("do not label everything High"). Top ~25% of the
    accepted batch -> High, next ~45% -> Medium, remaining ~30% -> Low."""
    n = len(items)
    if n == 0:
        return
    ranked = sorted(items, key=lambda x: x["opportunity_score"], reverse=True)
    high_cut = max(1, round(n * 0.25))
    medium_cut = max(high_cut + 1, round(n * 0.70))
    for i, item in enumerate(ranked):
        item["priority"] = "High" if i < high_cut else ("Medium" if i < medium_cut else "Low")


def assign_product_opportunity(query: str) -> str:
    tokens = tokenize(query)
    return "Yes" if len(tokens & PRODUCT_KEYWORDS) >= 1 and classify_intent(query) in (
        "How-To", "Recommendation", "Frequency") else "No"


# ---------------------------------------------------------------------------
# Harvesting
# ---------------------------------------------------------------------------

def harvest_pillar(pillar, seeds, target, dedup_pool, sources_available, stats):
    """Collects every candidate query for a pillar (bare-seed suggestions +
    full WHY/HOW/WHAT-style expansion + offline derived expansion), scores
    and filters all of them, then accepts the best `target` by Opportunity
    Score — so genuine question-form opportunities win over generic
    noun-phrase autocomplete completions, and near-duplicates keep
    whichever wording scored highest (section 19: 'keep the strongest
    wording')."""
    query_hits = {}  # normalized query -> (hit_count, best_rank, source, source_detail, seed)

    def record(text, source, source_detail, seed, rank=None):
        norm = normalize(text)
        if not norm:
            return
        if norm in query_hits:
            hits, best_rank, src, detail, sd = query_hits[norm]
            query_hits[norm] = (hits + 1, min(best_rank, rank) if rank is not None else best_rank, src, detail, sd)
        else:
            query_hits[norm] = (1, rank if rank is not None else 99, source, source_detail, seed)

    for seed in seeds:
        stats["seeds_researched"] += 1

        if "Google Autocomplete" in sources_available:
            results = fetch_suggest(seed.lower(), "firefox")
            if results is None:
                stats["source_call_failures"] += 1
            else:
                for i, r in enumerate(results):
                    record(r, "Google Autocomplete", f"autocomplete:{seed.lower()}", seed, i)
            for prefix in EXPANSION_PREFIXES:
                results = fetch_suggest(f"{prefix} {seed.lower()}", "firefox")
                if results is None:
                    stats["source_call_failures"] += 1
                    continue
                for i, r in enumerate(results):
                    record(r, "Google Autocomplete", f"autocomplete:{prefix} {seed.lower()}", seed, i)
            for suffix in EXPANSION_SUFFIXES:
                results = fetch_suggest(f"{seed.lower()} {suffix}", "firefox")
                if results is None:
                    stats["source_call_failures"] += 1
                    continue
                for i, r in enumerate(results):
                    record(r, "Google Autocomplete", f"autocomplete:{seed.lower()} {suffix}", seed, i)

        if "YouTube" in sources_available:
            results = fetch_suggest(seed.lower(), "youtube")
            if results is None:
                stats["source_call_failures"] += 1
            else:
                for i, r in enumerate(results):
                    record(r, "YouTube", f"youtube-suggest:{seed.lower()}", seed, i)

        for q in derived_expansion_queries(seed):
            record(q, "Derived Search Intent", f"template-expansion:{seed.lower()}", seed)

    scored = []
    for norm, (hits, best_rank, source, source_detail, seed) in query_hits.items():
        stats["raw_opportunities"] += 1

        reason = is_off_niche_or_unsafe(norm)
        if reason:
            stats["rejected"] += 1
            continue

        if not (tokenize(norm) & PILLAR_TOKENS[pillar]):
            stats["rejected"] += 1
            continue
        relevance = score_audience_relevance(norm, pillar)

        potential = score_content_potential(norm)
        competition = score_competition(norm, seed)
        demand = score_search_demand(source, hits, None if best_rank == 99 else best_rank)
        opp = opportunity_score(relevance, potential, demand, competition)

        scored.append({
            "pillar": pillar, "seed": seed, "query": norm, "source": source,
            "source_detail": source_detail, "relevance": relevance, "potential": potential,
            "competition": competition, "demand": demand, "opportunity_score": opp,
            "priority": None, "intent": classify_intent(norm),
            "audience_level": classify_audience_level(norm),
            "product_opportunity": assign_product_opportunity(norm),
            "subcategory": SUBCATEGORY_MAP.get(seed, seed),
        })

    scored.sort(key=lambda x: x["opportunity_score"], reverse=True)

    # Cap how many accepted opportunities can come from the same seed, so a
    # handful of seeds that happen to score well (e.g. "Rest Days") don't
    # crowd out the rest of the pillar's seed library (e.g. Sleep, DOMS,
    # Mobility never getting picked at all).
    per_seed_cap = max(2, -(-target // len(seeds)) + 1)  # ceil(target/seeds) + 1
    per_seed_counts = {}

    accepted = []
    for item in scored:
        if len(accepted) >= target:
            break
        if per_seed_counts.get(item["seed"], 0) >= per_seed_cap:
            continue
        dup = dedup_pool.is_duplicate(item["query"])
        if dup == "exact":
            stats["duplicates_exact"] += 1
            continue
        if dup == "semantic":
            stats["duplicates_semantic"] += 1
            continue
        accepted.append(item)
        dedup_pool.add(item["query"])
        per_seed_counts[item["seed"]] = per_seed_counts.get(item["seed"], 0) + 1

    return accepted


# ---------------------------------------------------------------------------
# Sheet row construction
# ---------------------------------------------------------------------------

def build_search_bank_row(item, run_id: str, item_num: int, date_str: str) -> dict:
    search_id = f"VS-SEARCH-{date_str.replace('-', '')}-{run_id}-{item_num:03d}"
    return {
        "Search Query": item["query"],
        "Topic": build_topic_label(item["query"], item["seed"]),
        "Category": item["pillar"],
        "Search Intent": item["intent"],
        "Difficulty": "Low" if item["competition"] <= 3 else ("High" if item["competition"] >= 8 else "Medium"),
        "Search Score": int(round(item["opportunity_score"] * 10)),
        "Trend Score": int(round(item["demand"] * 10)),
        "Follower Potential": "High" if item["potential"] >= 8 else ("Low" if item["potential"] <= 4 else "Medium"),
        "Product Opportunity": item["product_opportunity"],
        "Status": STATUS_UNUSED,
        "Search ID": search_id,
        "Date Found": date_str,
        "Seed Topic": item["seed"],
        "Audience Problem": item["query"][0].upper() + item["query"][1:] if item["query"] else "",
        "Subcategory": item["subcategory"],
        "Audience Level": item["audience_level"],
        "Source": item["source"],
        "Source Detail": item["source_detail"],
        "Trend Signal": "Unknown",
        "Search Demand": item["demand"],
        "Audience Relevance": item["relevance"],
        "Content Potential": item["potential"],
        "Competition": item["competition"],
        "Opportunity Score": item["opportunity_score"],
        "Priority": item["priority"],
        "Date Used": "",
        "Notes": "",
    }


# ---------------------------------------------------------------------------
# Config / logging
# ---------------------------------------------------------------------------

def load_config():
    load_dotenv()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    email_to = os.environ.get("SUMMARY_EMAIL_TO")
    base_batch_size = int(os.environ.get("SEARCH_ENGINE_BATCH_SIZE", "50"))
    if not sheet_id:
        sys.exit("GOOGLE_SHEET_ID is not set in .env")
    return {"sheet_id": sheet_id, "email_to": email_to, "base_batch_size": base_batch_size}


def write_log(sheet_id, service, run_id, phase, trigger, extra=None):
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {"run_id": run_id, "phase": phase, "trigger": trigger}
    payload.update(extra or {})
    row = {
        "Date": now_iso,
        "Workflow": WORKFLOW_NAME,
        "Success": 1 if phase == "completed" and not (extra or {}).get("errors") else (
            0 if phase == "completed" else ""
        ),
        "Time": now_iso,
        "Errors": json.dumps(payload),
    }
    sheets_io.append_rows(sheet_id, AUTOMATION_LOGS_TAB, AUTOMATION_LOGS_HEADERS, [row], service=service)
    return now_iso


def parse_log_entry(row):
    """Best-effort parse of an Automation Logs row's JSON Errors payload.
    Returns {} for rows that don't participate in lock logic (legacy rows,
    other workflows)."""
    try:
        return json.loads(row.get("Errors") or "{}")
    except (TypeError, ValueError):
        return {}


def check_overlap(sheet_id, service):
    """Returns a blocking run_id if a previous Workflow 00 run is still
    within its stale-run window with no completed/skipped marker, else
    None. Mirrors the lock pattern in generate_content.py / quality_check.py
    — the sheet itself is the lock, no local lock files."""
    logs = sheets_io.read_tab(sheet_id, AUTOMATION_LOGS_TAB, service=service)
    workflow_logs = [
        (r, parse_log_entry(r)) for r in logs if r.get("Workflow") == WORKFLOW_NAME
    ]

    started = {}
    resolved_run_ids = set()
    for row, payload in workflow_logs:
        run_id, phase = payload.get("run_id"), payload.get("phase")
        if not run_id or not phase:
            continue
        if phase == "started":
            started[run_id] = row.get("Date")
        elif phase in ("completed", "skipped"):
            resolved_run_ids.add(run_id)

    now = datetime.now(timezone.utc)
    for run_id, started_at in started.items():
        if run_id in resolved_run_ids:
            continue
        try:
            started_dt = datetime.fromisoformat(started_at)
        except (TypeError, ValueError):
            continue
        if now - started_dt < timedelta(minutes=STALE_RUN_TIMEOUT_MINUTES):
            return run_id
    return None


def distribute_batch(batch_size: int, pillars: list) -> dict:
    base = batch_size // len(pillars)
    remainder = batch_size % len(pillars)
    result = {}
    for i, p in enumerate(pillars):
        result[p] = base + (1 if i < remainder else 0)
    return result


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(dry_run: bool, batch_size_override, send_email: bool, trigger: str):
    cfg = load_config()
    sheet_id = cfg["sheet_id"]
    service = sheets_io.get_sheets_service()
    batch_size = batch_size_override or cfg["base_batch_size"]
    pillars = list(SEED_TOPICS.keys())
    targets = distribute_batch(batch_size, pillars)

    run_id = str(uuid.uuid4().int)[:4]
    date_str = datetime.now(timezone.utc).date().isoformat()
    start_time = time.monotonic()

    print(f"Run ID: {run_id} | Trigger: {trigger} | Batch size: {batch_size} "
          f"(targets: {targets})")

    if not dry_run:
        blocking_run_id = check_overlap(sheet_id, service)
        if blocking_run_id:
            reason = f"previous run '{blocking_run_id}' still active (started < {STALE_RUN_TIMEOUT_MINUTES}m ago)"
            write_log(sheet_id, service, run_id, "skipped", trigger, {"reason": reason})
            print(f"SKIPPED: {reason}")
            return
        write_log(sheet_id, service, run_id, "started", trigger)

    print("Checking research source availability...")
    sources_available, sources_unavailable = check_source_availability()
    print(f"  Available: {sources_available}")
    for name, reason in sources_unavailable:
        print(f"  Unavailable: {name} ({reason})")

    print("Reading existing Search Bank + Content Pipeline for dedup context...")
    existing_search_bank = sheets_io.read_tab(sheet_id, SEARCH_BANK_TAB, service=service)
    existing_content_pipeline = sheets_io.read_tab(sheet_id, CONTENT_PIPELINE_TAB, service=service)
    pipeline_row_count_before = len(existing_content_pipeline)

    dedup_pool = DedupPool()
    for r in existing_search_bank:
        if r.get("Search Query"):
            dedup_pool.add(r["Search Query"])
    for r in existing_content_pipeline:
        for field in ("Topic", "Search Query"):
            if r.get(field):
                dedup_pool.add(r[field])

    stats = {
        "seeds_researched": 0, "raw_opportunities": 0, "duplicates_exact": 0,
        "duplicates_semantic": 0, "rejected": 0, "source_call_failures": 0,
    }

    accepted_by_pillar = {}
    for pillar in pillars:
        accepted_by_pillar[pillar] = harvest_pillar(
            pillar, SEED_TOPICS[pillar], targets[pillar], dedup_pool, sources_available, stats
        )

    all_accepted = [item for items in accepted_by_pillar.values() for item in items]
    assign_priorities_by_rank(all_accepted)
    all_accepted.sort(key=lambda x: x["opportunity_score"], reverse=True)

    rows_to_write = [
        build_search_bank_row(item, run_id, i + 1, date_str)
        for i, item in enumerate(all_accepted)
    ]

    duration = round(time.monotonic() - start_time, 2)
    accepted_count = len(rows_to_write)
    high_priority = sum(1 for r in rows_to_write if r["Priority"] == "High")
    fitness_n = len(accepted_by_pillar["Fitness"])
    nutrition_n = len(accepted_by_pillar["Nutrition"])
    recovery_n = len(accepted_by_pillar["Recovery"])

    print(f"\nAccepted {accepted_count} opportunities "
          f"(Fitness={fitness_n}, Nutrition={nutrition_n}, Recovery={recovery_n}, High priority={high_priority})")
    print(f"Raw opportunities considered: {stats['raw_opportunities']} | "
          f"Exact dupes removed: {stats['duplicates_exact']} | "
          f"Semantic dupes removed: {stats['duplicates_semantic']} | "
          f"Quality-filter rejected: {stats['rejected']}")

    top10 = sorted(rows_to_write, key=lambda r: r["Opportunity Score"], reverse=True)[:10]
    print("\nTop 10 by Opportunity Score:")
    for r in top10:
        print(f"  [{r['Opportunity Score']}] ({r['Priority']}, {r['Category']}) {r['Search Query']}  <- {r['Source']}")

    if dry_run:
        print("\n--dry-run: stopping before any Sheets writes, log entry, or email.")
        return

    errors = []
    try:
        sheets_io.ensure_headers(sheet_id, SEARCH_BANK_TAB, SEARCH_BANK_REQUIRED_HEADERS, service=service)
        sheets_io.append_rows(sheet_id, SEARCH_BANK_TAB, SEARCH_BANK_REQUIRED_HEADERS, rows_to_write, service=service)
    except Exception as e:
        errors.append(f"Search Bank write failed: {e}")
        print(f"\nERROR: {errors[-1]}")
        write_log(sheet_id, service, run_id, "completed", trigger, {
            "accepted": 0, "attempted": accepted_count, "errors": errors,
            "duration_seconds": duration,
        })
        sys.exit("Search Bank write failed — research was NOT stored. See error above.")

    pipeline_after = sheets_io.read_tab(sheet_id, CONTENT_PIPELINE_TAB, service=service)
    pipeline_untouched = len(pipeline_after) == pipeline_row_count_before

    log_extra = {
        "seeds_researched": stats["seeds_researched"],
        "sources_checked": sources_available,
        "sources_unavailable": [n for n, _ in sources_unavailable],
        "raw_opportunities": stats["raw_opportunities"],
        "duplicates_exact": stats["duplicates_exact"],
        "duplicates_semantic": stats["duplicates_semantic"],
        "rejected": stats["rejected"],
        "accepted": accepted_count,
        "fitness": fitness_n, "nutrition": nutrition_n, "recovery": recovery_n,
        "high_priority": high_priority,
        "duration_seconds": duration,
        "content_pipeline_untouched": pipeline_untouched,
        "errors": errors,
    }
    write_log(sheet_id, service, run_id, "completed", trigger, log_extra)

    print(f"\nAppended {accepted_count} row(s) to Search Bank. Content Pipeline untouched: {pipeline_untouched}.")

    if send_email and cfg["email_to"]:
        subject = f"Vital Sync Search Intelligence — {accepted_count} new opportunities ({date_str})"
        body_lines = [
            f"Run ID: {run_id} | Trigger: {trigger} | Duration: {duration}s",
            f"Accepted: {accepted_count} (Fitness={fitness_n}, Nutrition={nutrition_n}, Recovery={recovery_n}, High priority={high_priority})",
            f"Raw opportunities: {stats['raw_opportunities']} | Exact dupes: {stats['duplicates_exact']} | "
            f"Semantic dupes: {stats['duplicates_semantic']} | Rejected: {stats['rejected']}",
            f"Sources available: {', '.join(sources_available)}",
            f"Sources unavailable: {', '.join(n for n, _ in sources_unavailable)}",
            "", "Top 10 by Opportunity Score:",
        ]
        for r in top10:
            body_lines.append(f"  [{r['Opportunity Score']}] ({r['Priority']}) {r['Search Query']}")
        try:
            gmail_send.send_email(cfg["email_to"], subject, "\n".join(body_lines))
            print(f"Summary emailed to {cfg['email_to']}.")
        except Exception as e:
            print(f"Email send failed (non-fatal): {e}")


def _cli():
    parser = argparse.ArgumentParser(description="Vital Sync Workflow 00 — Search Intelligence Engine")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview only — no Sheets writes, no log, no email")
    mode.add_argument("--live", action="store_true", help="Full run: appends to Search Bank, logs, emails summary")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run, batch_size_override=args.batch_size,
        send_email=not args.no_email, trigger=args.trigger)


if __name__ == "__main__":
    _cli()
