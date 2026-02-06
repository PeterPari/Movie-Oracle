import hashlib
import threading
from tenacity import retry, stop_after_attempt, wait_exponential
from backend.cache import db_cache
from google import genai
import os
import json
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

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
**tmdb_keyword_tags**: TMDb keyword slugs for themes/tropes. Examples: time-travel, heist, revenge, twist-ending, based-on-true-story, dystopia, coming-of-age, survival, serial-killer, alien, zombie, haunted-house, road-trip, underdog, conspiracy, artificial-intelligence, vampire, superhero, prison, treasure, bounty-hunter
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
{"strategies":["discover"],"keywords":"comfort movies feel good","tmdb_keyword_tags":["feel-good","heartwarming"],"genres":["comedy","drama","romance"],"exclude_genres":["horror","thriller"],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":200,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Wrapping you in cinema's warmest blanket — guaranteed soul-soothing picks"}

Query: "movies that will mess with my head"
{"strategies":["discover"],"keywords":"mind bending psychological","tmdb_keyword_tags":["twist-ending","nonlinear-timeline","psychological","mindfuck"],"genres":["thriller","science fiction","mystery"],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":300,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Prepare for cerebral cinema that'll have you questioning reality long after the credits roll"}

Query: "Tom Hanks 90s dramas"
{"strategies":["discover"],"keywords":"Tom Hanks 90s drama","tmdb_keyword_tags":[],"genres":["drama"],"exclude_genres":[],"companies":[],"actors":["Tom Hanks"],"directors":[],"crew":[],"year_from":1990,"year_to":1999,"min_rating":null,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Diving into Hanks' finest dramatic work from the decade that cemented his legend"}

Query: "movies like Parasite"
{"strategies":["similar"],"keywords":"Parasite","tmdb_keyword_tags":["social-commentary","dark-humor","class-differences"],"genres":["thriller","drama"],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":"Parasite","runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Hunting for films that match Parasite's razor-sharp social satire and genre-bending brilliance"}

Query: "A24 horror"
{"strategies":["discover"],"keywords":"A24 horror","tmdb_keyword_tags":["psychological","slow-burn"],"genres":["horror"],"exclude_genres":[],"companies":["A24"],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":6.0,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Summoning A24's finest — elevated horror that haunts your mind, not just your nightmares"}

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

def _call_gemini_with_retry(model, contents, config):
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _safe_generate_content(model, contents, config):
    return _call_gemini_with_retry(model, contents, config)

def _call_gemini(system_prompt, user_prompt, temperature=0.3):
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
                    "max_output_tokens": 1500,
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

def extract_search_params(query):
    try:
        content = _call_gemini(EXTRACT_SYSTEM_PROMPT, query, temperature=0.2)
        params = _parse_json_response(content)
        # Defaults
        defaults = {
            "strategies": ["discover"], "keywords": query, "tmdb_keyword_tags": [],
            "genres": [], "companies": [], "sort_by": "popularity.desc",
            "explanation": f"Exploring: {query}"
        }
        for k, v in defaults.items():
            params.setdefault(k, v)
        return params
    except Exception as e:
        print(f"AI extraction failed: {e}")
        # Use discover for natural language fallback, not title_search
        return {
            "strategies": ["discover"],
            "keywords": query,
            "genres": [],
            "tmdb_keyword_tags": [],
            "sort_by": "popularity.desc",
            "min_votes": 50,
            "explanation": f"Exploring: {query}"
        }

def rank_and_explain(query, movies):
    movie_summaries = []
    for m in movies:
        movie_summaries.append({
            "tmdb_id": m.get("tmdb_id"),
            "title": m.get("title"),
            "year": m.get("year"),
            "overview": m.get("overview", "")[:300],
            "tmdb_rating": m.get("tmdb_rating"),
            "imdb_rating": m.get("imdb_rating"),
            "rotten_tomatoes": m.get("rotten_tomatoes"),
            "director": m.get("director"),
            "budget": m.get("budget"),
            "revenue": m.get("revenue"),
            "keywords": m.get("keywords")
        })

    user_content = f"User query: {query}\n\nCandidate movies:\n{json.dumps(movie_summaries, indent=2)}"

    try:
        content = _call_gemini(RANK_SYSTEM_PROMPT, user_content, temperature=0.4)
        return _parse_json_response(content)
    except Exception:
        return {
            "summary": "Here are the movies I found:",
            "ranked_movies": [{"tmdb_id": m.get("tmdb_id"), "rank": i+1, "oracle_score": None, "relevance_explanation": ""} for i, m in enumerate(movies)]
        }
