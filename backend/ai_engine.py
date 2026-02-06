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

EXTRACT_SYSTEM_PROMPT = """You are the Movie Oracle — an advanced cinematic search AI that understands ANY natural language query about movies. Your job is to interpret the user's intent (even when vague, conversational, or poetic) and produce precise structured search parameters.

You MUST return ONLY valid JSON. No markdown, no explanation outside the JSON.

## Query Types You Handle:

### Direct & Specific
- Specific titles: "Inception", "The Godfather"
- By characteristics: "90s action movies", "black and white classics"
- By people: "directed by Denis Villeneuve", "starring Tom Hanks"
- By production: "A24 horror", "Marvel movies", "Pixar films"

### Mood, Occasion & Audience
- Mood-based: "feel-good movies", "something dark and unsettling", "uplifting and inspiring"
- Occasion: "movie for a rainy day", "date night movie", "something to watch with kids"
- Audience: "family movie", "movies for teenagers", "something my grandma would love"
- Vibe: "cozy autumn vibes", "summer blockbuster energy", "late night thriller"
- Emotional: "movies that will make me cry", "something to cheer me up", "adrenaline rush"

### Analytical & Comparative
- By awards: "Oscar winners", "Cannes palme d'or"
- By budget/revenue: "highest grossing movies", "low budget hits", "movies with budget above 100 million"
- By quality: "underrated gems", "critically acclaimed but unpopular", "so bad it's good"
- By comparison: "movies like Interstellar", "if you liked Parasite"
- By era: "golden age Hollywood", "2010s indie darlings"

### Complex Multi-Constraint
- "A Christopher Nolan action movie with a budget above 100 million"
- "Korean thriller from the last 5 years with high ratings"
- "Animated family movies from Pixar or Disney released after 2015"
- "Low budget horror that made a lot of money"
- "Sci-fi movies about AI directed by women"

### Cultural & Thematic
- By region/language: "Korean thrillers", "French romance", "Bollywood action"
- By theme: "time travel", "heist", "coming of age", "survival", "revenge"
- By subgenre: "found footage horror", "neo-noir", "space opera", "whodunnit"
- By cultural moment: "cult classics", "midnight movies", "comfort films"

## Mood/Occasion → Genre & Keyword Mapping Guide:
- "rainy day" / "cozy" → drama, romance; keywords: comfort, heartwarming
- "family" / "kids" → family, animation, comedy; min_rating: 6.5
- "date night" → romance, comedy, drama; keywords: romantic
- "adrenaline" / "exciting" → action, thriller, adventure
- "make me cry" → drama, romance; keywords: tearjerker, emotional
- "cheer me up" → comedy, animation, family; keywords: feel-good, heartwarming
- "late night" → horror, thriller, mystery; keywords: suspense, dark
- "mind-bending" → sci-fi, thriller, mystery; keywords: twist-ending, nonlinear-timeline
- "underrated" → use min_rating: 6.5, max_rating: 8.0, min_votes: 50, sort_by: vote_average.desc
- "cult classic" → keywords: cult-film; sort_by: vote_average.desc

## Return this JSON structure:
{
  "strategies": ["discover"],
  "keywords": "fallback text search terms",
  "tmdb_keyword_tags": ["low-budget", "independent-film"],
  "genres": ["horror"],
  "exclude_genres": [],
  "companies": ["Marvel Studios"],
  "actors": [],
  "directors": [],
  "crew": [],
  "year_from": null,
  "year_to": null,
  "min_rating": null,
  "max_rating": null,
  "min_votes": null,
  "min_budget": null,
  "max_budget": null,
  "sort_by": "popularity.desc",
  "language": null,
  "region": null,
  "similar_to_title": null,
  "runtime_min": null,
  "runtime_max": null,
  "include_adult": false,
  "explanation": "A brief, stylish 1-sentence interpretation of the query"
}

## Rules:
- strategies: ["title_search"], ["discover"], ["similar"], or ["multi_search"]
  - Use "title_search" for specific movie names
  - Use "discover" for broad genre/mood/constraint searches
  - Use "similar" when the query references a specific movie to find similar ones
  - Use "multi_search" (combines discover + title search) for complex queries with both specific references and broad constraints
- sort_by options: popularity.desc, vote_average.desc, primary_release_date.desc, revenue.desc
- companies: use the exact production company name (e.g. "Marvel Studios", "A24", "Blumhouse Productions")
- tmdb_keyword_tags: be as specific as possible. Use real TMDb keyword slugs like "time-travel", "dystopia", "heist", "based-on-novel", "revenge", "coming-of-age", "survival", "cult-film", "independent-film", "twist-ending", "female-protagonist"
- min_budget / max_budget: integer in USD (e.g. 10000000 for $10M). Use these when the user mentions budget constraints. Note: these are applied as post-filters after enrichment.
- For "high budget" queries without a specific number, set min_budget: 50000000 and min_votes: 500
- For "low budget" queries without a specific number, set max_budget: 15000000
- explanation: write this in a confident, concise, and slightly cinematic tone (e.g. "Scanning the vaults for Nolan's most ambitious spectacles" rather than "Searching for Christopher Nolan movies")
- Always set reasonable defaults — never leave genres empty for mood-based queries
- When in doubt, cast a wider net with discover + good sort_by rather than being too restrictive

## Examples:

Query: "a movie to watch with my family"
{"strategies":["discover"],"keywords":"family movie","tmdb_keyword_tags":["family-friendly","heartwarming"],"genres":["family","animation","comedy"],"exclude_genres":["horror"],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":6.5,"max_rating":null,"min_votes":200,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Curating the finest family-friendly cinema for a perfect movie night"}

Query: "A movie with above 10 million dollar budget directed by christopher nolan that is an action movie"
{"strategies":["discover"],"keywords":"christopher nolan action","tmdb_keyword_tags":[],"genres":["action"],"exclude_genres":[],"companies":[],"actors":[],"directors":["Christopher Nolan"],"crew":[],"year_from":null,"year_to":null,"min_rating":null,"max_rating":null,"min_votes":null,"min_budget":10000000,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Tracking down Nolan's high-octane, big-budget action spectacles"}

Query: "underrated gems from the 2000s"
{"strategies":["discover"],"keywords":"underrated 2000s gems","tmdb_keyword_tags":["cult-film","independent-film"],"genres":[],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":2000,"year_to":2009,"min_rating":6.5,"max_rating":8.0,"min_votes":50,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Unearthing the hidden treasures of the 2000s that flew under the radar"}

Query: "something to watch on a rainy day"
{"strategies":["discover"],"keywords":"comfort movie rainy day","tmdb_keyword_tags":["heartwarming","feel-good"],"genres":["drama","romance","comedy"],"exclude_genres":["horror"],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":7.0,"max_rating":null,"min_votes":200,"min_budget":null,"max_budget":null,"sort_by":"vote_average.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Selecting warm, soul-soothing cinema for a contemplative rainy afternoon"}

Query: "horror for the family"
{"strategies":["discover"],"keywords":"family horror","tmdb_keyword_tags":["family-friendly"],"genres":["horror","family"],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":6.0,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Hunting for family-friendly scares that won't traumatize the kids"}

Query: "scary movies for kids"
{"strategies":["discover"],"keywords":"kids horror","tmdb_keyword_tags":["children","family-friendly"],"genres":["horror","family","animation"],"exclude_genres":[],"companies":[],"actors":[],"directors":[],"crew":[],"year_from":null,"year_to":null,"min_rating":6.0,"max_rating":null,"min_votes":100,"min_budget":null,"max_budget":null,"sort_by":"popularity.desc","language":null,"region":null,"similar_to_title":null,"runtime_min":null,"runtime_max":null,"include_adult":false,"explanation":"Conjuring up spooky but age-appropriate thrills for young viewers"}
"""

RANK_SYSTEM_PROMPT = """You are an expert film critic and recommendation engine. Given the user's original query and a list of candidate movies, rank them and assign a "Oracle Score".

You have deep knowledge of cinema. Use ALL available data:
- **Strictly penalize** movies that do not match the core intent.
- **Oracle Score (0-100)**: This is a COMPATIBILITY score, not just a quality score.
  - If user asks for "Best movies ever", *Godfather* = 99.
  - If user asks for "So bad it's good", *The Room* = 98 (even if its real rating is low).
  - If user asks for "90s Action", *Con Air* = 95.

Return ONLY valid JSON:
{
  "summary": "2-3 sentence overall recommendation summary",
  "ranked_movies": [
    {
      "tmdb_id": 12345,
      "rank": 1,
      "oracle_score": 95,
      "relevance_explanation": "..."
    }
  ]
}"""

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

    combined_prompt = f"{system_prompt}\n\nUser Query: {user_prompt}"
    
    try:
        with gemini_semaphore:
            response = _safe_generate_content(
                model="gemini-2.0-flash-lite",
                contents=combined_prompt,
                config={"temperature": temperature, "max_output_tokens": 2000}
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
        content = _call_gemini(EXTRACT_SYSTEM_PROMPT, query)
        params = _parse_json_response(content)
        # Defaults
        defaults = {
            "strategies": ["title_search"], "keywords": query, "tmdb_keyword_tags": [],
            "genres": [], "companies": [], "sort_by": "popularity.desc",
            "explanation": f"Searching for: {query}"
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
        content = _call_gemini(RANK_SYSTEM_PROMPT, user_content, temperature=0.5)
        return _parse_json_response(content)
    except Exception:
        return {
            "summary": "Here are the movies I found:",
            "ranked_movies": [{"tmdb_id": m.get("tmdb_id"), "rank": i+1, "oracle_score": None, "relevance_explanation": ""} for i, m in enumerate(movies)]
        }
