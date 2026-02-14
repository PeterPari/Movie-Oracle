import hashlib
import threading
import re
from tenacity import retry, stop_after_attempt, wait_exponential
from backend.cache import db_cache
try:
    from google import genai
except Exception:  # google-genai not installed / unavailable in this environment
    genai = None

import os
import json
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if (genai and GEMINI_API_KEY) else None

# Limit concurrent Gemini calls
gemini_semaphore = threading.Semaphore(5)

GENRE_MAP = {
    "action": 28, "adventure": 12, "animation": 16, "comedy": 35, "crime": 80,
    "documentary": 99, "drama": 18, "family": 10751, "fantasy": 14, "history": 36,
    "horror": 27, "music": 10402, "mystery": 9648, "romance": 10749, "science fiction": 878,
    "sci-fi": 878, "tv movie": 10770, "thriller": 53, "war": 10752, "western": 37,
}

EXTRACT_SYSTEM_PROMPT = """You are the Movie Oracle — an expert AI movie concierge with encyclopedic film knowledge. Your job: translate ANY natural language query into precise TMDb search parameters.

## CORE RULES
1. Return ONLY valid JSON — no markdown fences, no commentary
2. Default strategy is "discover" unless query names a SPECIFIC movie title
3. Interpret MEANING, not literal words. "something to cry to" = emotional dramas, not movies with the word "cry"
4. Use multiple genres when appropriate — most vibes span genres
5. tmdb_keyword_tags are powerful — use them for themes, tropes, and content types
6. Always write a witty, stylish "explanation" (1 sentence) — users see this first

## STRATEGY SELECTION
- **"discover"** (90% of queries): genre/actor/director/year/keyword/rating filtering
- **"title_search"**: ONLY when user wants a SPECIFIC movie by name ("show me Inception", "find The Matrix")
- **"similar"**: "like X", "similar to X", "if I liked X" → set similar_to_title
- **"multi_search"**: queries mixing references + constraints ("something like Inception but from the 80s")

## PARAMETER GUIDE

**People**: actors[], directors[] — use full canonical names (e.g. "Bryan Cranston" not "that guy from Breaking Bad")
**Genres**: Use TMDb genre names: action, adventure, animation, comedy, crime, documentary, drama, family, fantasy, history, horror, music, mystery, romance, science fiction, thriller, war, western
**tmdb_keyword_tags**: ONLY use keywords from this verified list (these are real TMDb keywords that will actually work):
  Themes: heist, revenge, dystopia, conspiracy, survival, prison, treasure, underdog, redemption, jealousy, fate, betrayal, friendship, love triangle, obsession, ambition, isolation, sacrifice, corruption, propaganda
  Tropes: twist ending, based on true story, time travel, coming of age, fish out of water, road trip, found footage, haunted house, buddy cop, chase, mistaken identity, rescue, one man army, against the odds, chosen one
  Vibes: feel good, heartwarming, dark humor, cult, surreal, atmospheric, gritty, noir, campy, dreamlike, offbeat, quirky, absurdist, cerebral, visceral, psychological, slow burn, suspenseful, mind-bending
  Creatures: alien, zombie, vampire, superhero, serial killer, bounty hunter, robot, dragon, dinosaur, ghost, monster, werewolf, witch, demon, pirate
  Settings: space, underwater, desert, jungle, post-apocalyptic future, small town, new york city, hospital, school, courtroom, prison, arctic, island
  Content: independent film, b movie, anime, mockumentary, anthology, musical, satire, parody, remake, sequel, prequel, biography, documentary
  IMPORTANT: Use spaces, not hyphens (e.g. "time travel" not "time-travel", "coming of age" not "coming-of-age"). Pick 2-4 tags max. Only use tags from this list.
**companies**: Studio names exactly as TMDb has them: "A24", "Marvel Studios", "Pixar", "Studio Ghibli", "Blumhouse Productions", "Focus Features", "Lionsgate"
**Budget**: min_budget/max_budget in raw dollars. "low budget" ≈ max_budget: 5000000. "big budget" ≈ min_budget: 80000000
**Ratings**: min_rating/max_rating on TMDb 0-10 scale. "good" ≈ 7.0+, "great" ≈ 7.5+, "masterpiece" ≈ 8.0+
**Votes**: min_votes filters obscure movies. 50=include niche, 200=mainstream, 1000=well-known only
**Language**: ISO 639-1 codes — ko, fr, es, de, ja, hi, zh, it, pt, ru, sv, da, no, fi, nl, pl, tr, ar, th
**sort_by**: popularity.desc (default), vote_average.desc, revenue.desc, primary_release_date.desc

## JSON SCHEMA
{"strategies":["discover"],"keywords":"fallback search terms","tmdb_keyword_tags":[],"genres":[],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":null,"max_rating":null,"min_votes":null,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Your stylish interpretation"}

## EXAMPLES

Query: "comfort movies"
{"strategies":["discover"],"keywords":"comfort movies feel good","tmdb_keyword_tags":["feel good","heartwarming"],"genres":["comedy","drama","romance"],"exclude_genres":["horror","thriller"],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":200,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Wrapping you in cinema's warmest blanket — guaranteed soul-soothing picks"}

Query: "movies that will mess with my head"
{"strategies":["discover"],"keywords":"mind bending psychological","tmdb_keyword_tags":["twist ending","psychological","cerebral"],"genres":["thriller","science fiction","mystery"],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":300,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Prepare for cerebral cinema that'll have you questioning reality long after the credits roll"}

Query: "Tom Hanks 90s dramas"
{"strategies":["discover"],"keywords":"Tom Hanks 90s drama","tmdb_keyword_tags":[],"genres":["drama"],"exclude_genres":[],"companies":[],"actors":["Tom Hanks"],"directors":[],"crew":[],"year_from":1990,"year_to":1999,"min_rating":null,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Diving into Hanks' finest dramatic work from the decade that cemented his legend"}

Query: "movies like Parasite"
{"strategies":["similar"],"keywords":"Parasite","tmdb_keyword_tags":["dark humor","satire"],"genres":["thriller","drama"],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":"Parasite","runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Hunting for films that match Parasite's razor-sharp social satire and genre-bending brilliance"}

Query: "A24 horror"
{"strategies":["discover"],"keywords":"A24 horror","tmdb_keyword_tags":["psychological","slow burn"],"genres":["horror"],"exclude_genres":[],"companies":["A24"],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":6.0,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Summoning A24's finest — elevated horror that haunts your mind, not just your nightmares"}

Query: "what should I watch tonight"
{"strategies":["discover"],"keywords":"popular recent movies","tmdb_keyword_tags":[],"genres":[],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":2022,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":500,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Curating tonight's perfect lineup from the best recent releases"}
"""

RANK_SYSTEM_PROMPT = """You are the Movie Oracle's ranking engine. Given the user's query and candidate movies, rank them by RELEVANCE to the query and assign Oracle Scores.

## SCORING RULES
- Oracle Score (0-100) = how well this movie matches the USER'S INTENT
- This is NOT a quality score — it's a compatibility score
- "So bad it's good" query → The Room = 95, The Godfather = 40
- "90s action" query → Con Air = 92, The Matrix = 97
- Movies that don't match the query AT ALL should get scores below 50
- Be decisive: spread scores across the range, don't cluster everything at 80-90

## EXPLANATION RULES
- Keep relevance_explanation to 1 SHORT sentence (under 15 words)
- Focus on WHY it matches the query, not plot summaries
- Use punchy, confident language

## SUMMARY RULES
- Write 1-2 sentences as an overall recommendation blurb
- Reference the user's query intent
- Be stylish and authoritative

Return ONLY valid JSON, no markdown:
{"summary":"...","ranked_movies":[{"tmdb_id":12345,"rank":1,"oracle_score":95,"relevance_explanation":"..."}]}"""

TITLE_SYSTEM_PROMPT = """You are a movie recommendation assistant. Given a user query, return ONLY valid JSON with a list of 8-12 movie titles that match the intent.

Rules:
- Return ONLY valid JSON, no markdown
- Output format: {"titles":["Title 1","Title 2", ...]}
- Use well-known or cult titles that plausibly exist in TMDb
- Do NOT include years or extra commentary
"""

CHAT_SYSTEM_PROMPT = """You are Movie Oracle Chat, a smart movie assistant.

Behavior:
- Be natural, warm, and concise like a normal chatbot.
- Keep replies practical and specific (titles, genres, directors, eras, where useful).
- Ask one clarifying question only when the user's request is ambiguous.
- Treat each request independently. Do not rely on prior conversation context.
- Prefer grounded recommendations over hype.

Quality rules:
- For ANY user query (even if it's about work, life, school, travel, coding, stress, etc.), infer the vibe/themes and recommend relevant movies.
- Recommend 5 movies unless user asks otherwise.
- For each recommendation, include a short reason tied to the user's query.
- Never refuse just because the query is not explicitly about movies.

Output rules:
- Return plain text only (no JSON, no markdown fences).
- Keep default response length to a compact list.
"""

FLEX_ANY_QUERY_PROMPT = """You are a movie mapping engine.

Task: Convert ANY user query into relevant movie recommendations.

Rules:
- If query is not about movies, infer intent/themes/emotions and map to movies.
- Return exactly 5 recommendations unless user explicitly requests a different count.
- Recommendation reasons must be specific to the user's query intent.
- Use real, recognizable movie titles.
- Do not refuse or redirect.

Return ONLY valid JSON, no markdown:
{"intro":"one short sentence tying query to movie picks","recommendations":[{"title":"Movie Title","reason":"short reason"}]}
"""

def _call_gemini_with_retry(model, contents, config):
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _safe_generate_content(model, contents, config):
    return _call_gemini_with_retry(model, contents, config)

def _call_gemini(system_prompt, user_prompt, temperature=0.3):
    if client is None:
        return "{}"
    prompt_hash = hashlib.md5((system_prompt + user_prompt).encode()).hexdigest()
    cache_key = f"gemini:{prompt_hash}:{temperature}"

    cached_response = db_cache.get(cache_key)
    if cached_response:
        return cached_response

    try:
        with gemini_semaphore:
            response = _safe_generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": 1000,
                    "system_instruction": system_prompt,
                }
            )
        text_response = response.text
        db_cache.set(cache_key, text_response, ttl=86400)
        return text_response
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "{}"

def _parse_json_response(content):
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()
    return json.loads(content)

def _heuristic_params(query: str) -> dict:
    lowered = query.lower()
    params: dict = {}

    # Vibe mappings for common natural language queries
    vibe_map = {
        "comfort": {"tmdb_keyword_tags": ["feel good", "heartwarming"], "genres": ["comedy", "drama", "romance"], "exclude_genres": ["horror", "thriller"]},
        "feel good": {"tmdb_keyword_tags": ["feel good", "heartwarming"], "genres": ["comedy", "drama", "romance"], "exclude_genres": ["horror", "thriller"]},
        "cozy": {"tmdb_keyword_tags": ["feel good", "heartwarming"], "genres": ["comedy", "drama", "romance"]},
        "uplifting": {"tmdb_keyword_tags": ["feel good", "heartwarming"], "genres": ["comedy", "drama", "romance"]},
    }
    for key, vibe in vibe_map.items():
        if key in lowered:
            params.setdefault("tmdb_keyword_tags", []).extend(vibe.get("tmdb_keyword_tags", []))
            params.setdefault("genres", []).extend(vibe.get("genres", []))
            params.setdefault("exclude_genres", []).extend(vibe.get("exclude_genres", []))

    # Detect genres by keyword presence
    genre_hits = []
    genre_aliases = {
        "sci fi": "science fiction",
        "sci-fi": "science fiction",
        "scifi": "science fiction",
        "romcom": "romance",
        "rom-com": "romance",
    }
    for alias, canonical in genre_aliases.items():
        if alias in lowered:
            genre_hits.append(canonical)
    for g in GENRE_MAP.keys():
        if g in lowered:
            genre_hits.append(g)
    if genre_hits:
        existing = params.get("genres", [])
        params["genres"] = sorted(set(existing + genre_hits))

    # Director/actor patterns
    director_names = []
    actor_names = []
    by_match = re.search(r"(?:directed\s+by|by)\s+([a-zA-Z .'-]{3,})", query, re.IGNORECASE)
    if by_match:
        name = by_match.group(1).strip()
        name = re.split(r"\b(with|and|in|from|before|after|like)\b", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if len(name.split()) >= 2:
            director_names.append(name)
    starring_match = re.search(r"(?:starring|with)\s+([a-zA-Z .'-]{3,})", query, re.IGNORECASE)
    if starring_match:
        name = starring_match.group(1).strip()
        name = re.split(r"\b(and|in|from|before|after|like)\b", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if len(name.split()) >= 2:
            actor_names.append(name)

    last_name_match = re.search(r"([A-Z][a-z]+)\s+(movies|films|film|movie)$", query.strip())
    if last_name_match:
        director_names.append(last_name_match.group(1))

    if director_names:
        params["directors"] = director_names
    if actor_names:
        params["actors"] = actor_names

    # Years / decades
    decade_match = re.search(r"(19|20)\d0s", lowered)
    if decade_match:
        decade = int(decade_match.group(0)[:4])
        params["year_from"] = decade
        params["year_to"] = decade + 9
    year_range_match = re.search(r"\b(?:19|20)\d{2}\b\s*(?:-|to)\s*\b(?:19|20)\d{2}\b", lowered)
    if year_range_match:
        years = re.findall(r"\b(?:19|20)\d{2}\b", year_range_match.group(0))
        if len(years) >= 2:
            params["year_from"] = int(years[0])
            params["year_to"] = int(years[1])
    single_year_match = re.search(r"\b(19|20)\d{2}\b", lowered)
    if single_year_match and "year_from" not in params:
        year = int(single_year_match.group(0))
        params["year_from"] = year
        params["year_to"] = year

    # Similarity intent
    like_match = re.search(r"(?:like|similar to)\s+(.+)$", query, re.IGNORECASE)
    if like_match:
        title = like_match.group(1).strip()
        if title:
            params["similar_to_title"] = title
            params["strategies"] = ["similar"]

    return params

def extract_search_params(query):
    try:
        heuristic = _heuristic_params(query)
        content = _call_gemini(EXTRACT_SYSTEM_PROMPT, query, temperature=0.2)
        params = _parse_json_response(content)

        # Defaults (always ensure flexible strategies + keywords)
        defaults = {
            "strategies": ["discover"],
            "keywords": query,
            "tmdb_keyword_tags": [],
            "genres": [],
            "companies": [],
            "sort_by": "popularity.desc",
            "min_votes": 50,
            "explanation": f"Exploring: {query}"
        }
        for k, v in defaults.items():
            params.setdefault(k, v)
        # If a query looks like a specific title, add title_search strategy
        if len(query.split()) <= 5 and query.strip().lower().startswith(("show me ", "find ", "movie ", "film ", "watch ")):
            params["strategies"] = list({*params.get("strategies", []), "title_search"})
        # If AI returns empty-ish params, seed keyword tags from query terms
        if not params.get("tmdb_keyword_tags"):
            query_words = [w.lower() for w in query.split() if len(w) >= 3]
            params["tmdb_keyword_tags"] = query_words[:3]
        # Merge heuristic hints when AI left fields empty
        for key, value in heuristic.items():
            if key not in params or not params.get(key):
                params[key] = value
        params["_original_query"] = query
        return params
    except Exception as e:
        print(f"AI extraction failed: {e}")
        heuristic = _heuristic_params(query)
        query_words = [w.lower() for w in query.split() if len(w) >= 3]
        params = {
            "strategies": ["discover"],
            "keywords": query,
            "genres": [],
            "tmdb_keyword_tags": query_words[:3],
            "sort_by": "popularity.desc",
            "min_votes": 50,
            "_original_query": query,
            "explanation": f"Exploring: {query}"
        }
        if len(query.split()) <= 5:
            params["strategies"].append("title_search")
        for key, value in heuristic.items():
            params[key] = value
        return params

def rank_and_explain(query, movies):
    if client is None:
        return {
            "summary": "Here are the movies I found:",
            "ranked_movies": [{"tmdb_id": m.get("tmdb_id"), "rank": i+1, "oracle_score": None, "relevance_explanation": ""} for i, m in enumerate(movies)]
        }
    # Minimal payload to reduce AI tokens
    movie_summaries = [
        {
            "tmdb_id": m.get("tmdb_id"),
            "title": m.get("title"),
            "year": m.get("year"),
            "overview": (m.get("overview", "") or "")[:200],  # Truncated further
            "tmdb_rating": m.get("tmdb_rating"),
            "director": m.get("director"),
        }
        for m in movies
    ]

    user_content = f"User query: {query}\n\nCandidate movies:\n{json.dumps(movie_summaries)}"

    try:
        content = _call_gemini(RANK_SYSTEM_PROMPT, user_content, temperature=0.4)
        return _parse_json_response(content)
    except Exception:
        return {
            "summary": "Here are the movies I found:",
            "ranked_movies": [{"tmdb_id": m.get("tmdb_id"), "rank": i+1, "oracle_score": None, "relevance_explanation": ""} for i, m in enumerate(movies)]
        }

def suggest_titles(query: str) -> list:
    if client is None:
        return []
    try:
        content = _call_gemini(TITLE_SYSTEM_PROMPT, query, temperature=0.6)
        data = _parse_json_response(content)
        titles = data.get("titles", []) if isinstance(data, dict) else []
        if not isinstance(titles, list):
            return []
        # Clean and de-dup
        cleaned = []
        seen = set()
        for t in titles:
            if not t or not isinstance(t, str):
                continue
            name = t.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                cleaned.append(name)
        return cleaned[:12]
    except Exception:
        return []


def chat_with_oracle(messages: List[Dict[str, str]]) -> str:
    if client is None:
        return "I can help with movie recommendations, comparisons, genres, and watchlist ideas. Tell me your mood, favorite films, or what you're in the mood to watch tonight."

    latest_user_message = ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = (message.get("role") or "").strip().lower()
        content = (message.get("content") or "").strip()
        if role == "user" and content:
            latest_user_message = content[:2000]
            break

    if not latest_user_message:
        return "Tell me what kind of movie you're looking for, and I’ll give you focused picks."

    user_prompt = f"User request: {latest_user_message}\nAssistant:"

    try:
        content = _call_gemini(FLEX_ANY_QUERY_PROMPT, latest_user_message, temperature=0.6)
        data = _parse_json_response(content)
        intro = (data.get("intro") or "").strip()
        recommendations = data.get("recommendations", []) if isinstance(data, dict) else []
        rows = []
        for rec in recommendations[:5]:
            if not isinstance(rec, dict):
                continue
            title = (rec.get("title") or "").strip()
            reason = (rec.get("reason") or "").strip()
            if title:
                rows.append(f"- {title}: {reason}" if reason else f"- {title}")
        if rows:
            if intro:
                return f"{intro}\n" + "\n".join(rows)
            return "\n".join(rows)
    except Exception:
        pass

    try:
        response = _call_gemini(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.55)
        text = (response or "").strip()
        if text and "movie" in text.lower():
            return text
    except Exception:
        pass

    try:
        fallback_titles = suggest_titles(latest_user_message)
        if fallback_titles:
            picks = fallback_titles[:5]
            return "Here are relevant movie picks for your query:\n" + "\n".join([f"- {title}" for title in picks])
    except Exception:
        pass

    return "I can help you find the right movie fast. Share your mood, preferred genres, and whether you want something recent or classic."
