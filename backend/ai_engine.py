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

EXTRACT_SYSTEM_PROMPT = """You are an advanced movie search AI. Given ANY natural language query about movies, you must interpret the user's intent and produce structured search parameters. You can handle virtually any kind of movie question.

You MUST return ONLY valid JSON. No markdown, no explanation outside the JSON.

## Query Types You Handle:
- Specific titles: "Inception"
- By characteristics: "90s action movies"
- By people: "directed by Denis Villeneuve"
- By mood/theme: "feel-good movies"
- By comparison: "movies like Interstellar"
- By awards: "Oscar winners"
- By budget/revenue: "highest grossing movies", "low budget horror hits"
- By region/language: "Korean thrillers"
- Production: "A24 horror"

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
  "sort_by": "popularity.desc",
  "language": null,
  "region": null,
  "similar_to_title": null,
  "runtime_min": null,
  "runtime_max": null,
  "include_adult": false,
  "explanation": "Searching for high ROI horror films under small budgets"
}

## Rules:
- strategies: ["title_search"], ["discover"], ["similar"], or ["multi_search"]
- sort_by: popularity.desc, vote_average.desc, primary_release_date.desc, revenue.desc
- companies: specific production studios
- tmdb_keyword_tags: be specific (e.g. "time travel", "dystopia", "heist")
"""

RANK_SYSTEM_PROMPT = """You are an expert film critic and recommendation engine. Given the user's original query and a list of candidate movies with full details (ratings, budget, revenue, runtime, cast, crew, keywords, streaming info), rank and evaluate them.

You have deep knowledge of cinema. Use ALL available data to make intelligent rankings:
- **Strictly penalize** movies that do not match the core intent.
- **Commercial vs. Critical**: Prioritize ROI for "hits", Ratings for "masterpieces".
- **Budget Realism**: Check budget numbers for "low budget" queries.

Return ONLY valid JSON, no markdown:
{
  "summary": "2-3 sentence overall recommendation summary with personality and insight",
  "ranked_movies": [
    {
      "tmdb_id": 12345,
      "rank": 1,
      "score": 95,
      "relevance_explanation": "1-2 sentence explanation of why this matches, referencing specific data (ROI, Awards, Keywords)"
    }
  ]
}

**Score Calculation (0-100)**:
- Assign a 'score' to each movie.
- **90-100**: Perfect match for intent AND high quality/cult status.
- **75-89**: Good match, solid movie.
- **50-74**: Loose match or mediocre execution.
- **0-49**: Irrelevant or poor quality.
"""

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
                model="gemini-3-flash-preview", 
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
    except Exception:
        return {"strategies": ["title_search"], "keywords": query, "explanation": "Fallback search"}

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
            "ranked_movies": [{"tmdb_id": m.get("tmdb_id"), "rank": i+1, "score": None, "relevance_explanation": ""} for i, m in enumerate(movies)]
        }
