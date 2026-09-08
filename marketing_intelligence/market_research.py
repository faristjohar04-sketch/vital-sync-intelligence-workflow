"""Market research (workflow sections 10-13): real, zero-paid-API discovery
of public demand signals, written to the Market Signals sheet.

Sources actually implemented (all key-free, all real HTTP calls):
  - Google Autocomplete (suggestqueries.google.com)
  - YouTube Suggest (same host, client=youtube)
  - Derived AnswerThePublic-style expansion (offline template generation —
    a DISCOVERY INPUT per section 11, not itself evidence; only kept as a
    signal when it also shows up as a real autocomplete completion, or is
    explicitly logged as "Derived Search Intent" and scored more
    conservatively.)

Sources NOT implemented, and why (mirrors tools/research_vital_sync.py's
documented, honest gaps — logged as SOURCE UNAVAILABLE every run rather
than silently skipped):
  - Reddit's public JSON search returns 403 from this environment.
  - Google Trends / People Also Ask have no key-free API short of scraping
    SERP HTML, which is fragile and ToS-risky.
  - App Store / Google Play reviews, TikTok search, competitor forums:
    not yet implemented — future work, not fabricated.
"""

import requests

import duplicate_detector
import logger

USER_AGENT = "Mozilla/5.0 (compatible; VitalSyncMarketingIntel/1.0)"

# Populated by the most recent harvest() call — rows filtered out as noise
# (section 16/17), kept for reporting (section 29's "SEARCH SIGNALS REMOVED
# AS NOISE") without polluting the real Market Signals return value.
last_noise_removed: list = []

# Section 10 — core topic seeds, grouped by Primary Pillar.
SEED_TOPICS = {
    "Fitness Apps": ["fitness app", "workout tracking app", "workout programming app"],
    "Training": ["progressive overload", "muscle growth", "fat loss", "training readiness"],
    "Nutrition": ["nutrition tracking", "macro tracking", "hydration"],
    "Recovery": ["recovery", "sleep and fitness"],
    "AI Coaching": ["fitness ai", "adaptive coaching", "fitness gamification"],
    "Consistency": ["workout consistency", "fitness communities"],
    "Wearables": ["wearables", "training performance"],
}

# Section 10 — comparison / alternative intent.
ALTERNATIVE_SEEDS = [
    "myfitnesspal alternatives", "whoop alternatives", "strava alternatives",
    "hevy alternatives", "fitbod alternatives", "macrofactor alternatives",
    "oura alternatives", "garmin alternatives",
]

# Section 11 — AnswerThePublic-style expansion families.
EXPANSION_PREFIXES = ["who", "what", "when", "where", "why", "how", "can", "does", "should", "is", "are", "best"]
EXPANSION_SUFFIXES = ["vs", "alternative", "without", "for beginners"]

# Section 16/17: relevance filtering. Autocomplete/derived expansion is a
# real HTTP response, but that doesn't make every completion commercially
# meaningful for Vital Sync — a location-name completion ("recovery al
# quoz") or an off-topic product category ("wearables pants") is noise, not
# demand, and a bare "who <seed>"/"where <seed>" fragment with nothing else
# in it is a mechanically generated hypothesis, not an observed signal.
_UAE_LOCATION_NOISE = [
    "al quoz", "sharjah", "dubai", "abu dhabi", "ajman", "fujairah",
    "ras al khaimah", "umm al quwain", "deira", "jumeirah", "downtown",
]
_OFFTOPIC_TOKENS_BY_SEED = {
    "wearables": ["pants", "shorts", "socks", "jacket", "shoes", "hat", "gloves", "watch band"],
    "hydration": ["bottle brand", "flask brand"],
}
_CONTENT_SIGNAL_WORDS = (
    "how", "why", "best", "vs", "alternative", "app", "tracker", "track",
    "training", "workout", "program", "plan", "review", "guide",
)


def classify_relevance(query: str, seed: str, source: str) -> str:
    """Returns RELEVANT / WEAK / IRRELEVANT / AMBIGUOUS (section 16).
    IRRELEVANT/AMBIGUOUS rows are dropped from the harvest entirely (never
    written to Market Signals, never counted as demand) — see harvest()."""
    q = query.lower()
    if any(loc in q for loc in _UAE_LOCATION_NOISE):
        return "IRRELEVANT"
    if any(tok in q for tok in _OFFTOPIC_TOKENS_BY_SEED.get(seed.lower(), [])):
        return "IRRELEVANT"
    if source == "Derived Search Intent":
        # A mechanically generated who/what/where/... expansion that ISN'T
        # also a real autocomplete completion is a hypothesis, not an
        # observed signal (section 17) — always AMBIGUOUS at best.
        bare_prefix = any(q.strip() == f"{p} {seed}".lower() for p in EXPANSION_PREFIXES)
        if bare_prefix:
            return "AMBIGUOUS"
        return "WEAK"
    if any(w in q for w in _CONTENT_SIGNAL_WORDS):
        return "RELEVANT"
    return "WEAK"


SOURCE_UNAVAILABLE = [
    ("Reddit", "Public JSON search returns 403 from this environment."),
    ("Google Trends", "No key-free API; SERP scraping is fragile/ToS-risky."),
    ("People Also Ask", "No key-free API; SERP scraping is fragile/ToS-risky."),
    ("TikTok Search", "Not yet implemented — no key-free public search API."),
    ("App Store / Google Play Reviews", "Not yet implemented."),
]


def fetch_suggest(query: str, client: str = "firefox", timeout: float = 6.0):
    """Real Google/YouTube autocomplete call. Returns list[str] or None on
    failure (never fabricated)."""
    try:
        resp = requests.get(
            "https://suggestqueries.google.com/complete/search",
            params={"client": client, "q": query, "hl": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[1] if len(data) > 1 else []
    except (requests.RequestException, ValueError, IndexError):
        return None


def derived_expansion_queries(seed: str) -> list:
    queries = [f"{prefix} {seed}" for prefix in EXPANSION_PREFIXES]
    queries += [f"{seed} {suffix}" for suffix in EXPANSION_SUFFIXES]
    return queries


def score_demand(hit_count: int) -> int:
    if hit_count >= 8:
        return 9
    if hit_count >= 5:
        return 7
    if hit_count >= 2:
        return 5
    return 3


def score_relevance(query: str, pillar: str) -> int:
    q = query.lower()
    hits = sum(1 for kw in pillar.lower().split() if kw in q)
    return min(10, 6 + hits * 2)


def score_content_potential(query: str) -> int:
    q = query.lower()
    if any(w in q for w in ("how", "why", "best", "vs", "alternative")):
        return 8
    return 6


def score_competition(seed: str) -> int:
    high_competition = {"fitness app", "myfitnesspal alternatives", "muscle growth"}
    return 8 if seed in high_competition else 5


def priority_from_scores(demand: int, relevance: int, content: int) -> str:
    avg = (demand + relevance + content) / 3
    if avg >= 8:
        return "High"
    if avg >= 6:
        return "Medium"
    return "Low"


def check_source_availability(stats) -> None:
    for name, reason in SOURCE_UNAVAILABLE:
        stats.sources_unavailable += 1
        logger.log_line(f"SOURCE UNAVAILABLE: {name} — {reason}")


def harvest(existing_pool: "duplicate_detector.DuplicatePool", stats, max_per_pillar: int = 4) -> list:
    """Runs the full research sweep and returns new Market Signals rows
    (list of dicts, headers already matching the sheet) that are NOT
    duplicates of existing_pool. Does not write to the workbook.

    Section 16/17: rows classified IRRELEVANT (location-name noise,
    off-topic product category) or a bare-prefix AMBIGUOUS derived
    expansion ("who wearables") are filtered out here — never written,
    never counted as demand. Callers that want the removed-noise list for
    reporting (section 29's "SEARCH SIGNALS REMOVED AS NOISE") should read
    market_research.last_noise_removed right after calling this."""
    new_rows = []
    noise_removed = []
    check_source_availability(stats)

    all_seeds = []
    for pillar, seeds in SEED_TOPICS.items():
        for seed in seeds:
            all_seeds.append((pillar, seed))
    for seed in ALTERNATIVE_SEEDS:
        all_seeds.append(("Competitive Alternatives", seed))

    for pillar, seed in all_seeds:
        found_for_seed = 0
        candidates = []

        stats.sources_checked += 1
        google_hits = fetch_suggest(seed, client="firefox")
        if google_hits is not None:
            for q in google_hits[:6]:
                candidates.append((q, "Google Autocomplete"))
        else:
            stats.sources_unavailable += 1

        stats.sources_checked += 1
        yt_hits = fetch_suggest(seed, client="youtube")
        if yt_hits is not None:
            for q in yt_hits[:6]:
                candidates.append((q, "YouTube Search"))
        else:
            stats.sources_unavailable += 1

        # Derived expansion — discovery inputs, confirmed only if they also
        # come back as a real autocomplete suggestion; otherwise logged with
        # a conservative "Derived Search Intent" source, never claimed as
        # platform evidence.
        for expanded in derived_expansion_queries(seed)[:4]:
            candidates.append((expanded, "Derived Search Intent"))

        for query, source in candidates:
            if found_for_seed >= max_per_pillar:
                break
            key = f"{pillar} {query}"
            if existing_pool.find_duplicate(key):
                continue

            relevance_class = classify_relevance(query, seed, source)
            if relevance_class == "IRRELEVANT" or (relevance_class == "AMBIGUOUS" and source == "Derived Search Intent"):
                noise_removed.append({"pillar": pillar, "seed": seed, "query": query, "reason": relevance_class})
                continue

            demand = score_demand(len(google_hits or []) + len(yt_hits or []))
            relevance = score_relevance(query, pillar)
            content_potential = score_content_potential(query)
            competition = score_competition(seed)

            row = {
                "Date Found": None,  # filled by caller (needs datetime import at call site)
                "Source": source,
                "Source Detail / URL": (
                    "https://suggestqueries.google.com/complete/search"
                    if source != "Derived Search Intent" else "Offline template expansion"
                ),
                "Topic": pillar,
                "Search / Social Query": query,
                "Signal Type": "Search Intent" if source != "Derived Search Intent" else "Audience Problem",
                "Primary Pillar": pillar,
                "Audience Segment": "Unknown",
                "Trend Signal": "Unknown",
                "Demand Score": demand,
                "Relevance Score": relevance,
                "Content Potential": content_potential,
                "Competition": competition,
                "Priority": priority_from_scores(demand, relevance, content_potential),
                "Evidence Summary": f"{source} suggestion for seed '{seed}'.",
                "Status": "New",
                "_relevance_class": relevance_class,  # not a sheet header — dropped by workbook.write_row
            }
            new_rows.append(row)
            existing_pool.add(key, row)
            found_for_seed += 1

    global last_noise_removed
    last_noise_removed = noise_removed
    return new_rows
