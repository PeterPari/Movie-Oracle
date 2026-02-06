import os
import requests
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from backend.ai_engine import GENRE_MAP

# Load environment variables
load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
OMDB_BASE = "http://www.omdbapi.com/"

# Reusable session for connection pooling
_session = requests.Session()


class SQLiteCache:
    def __init__(self, db_path="movie_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        expiry INTEGER
                    )
                """)
        except Exception as e:
            print(f"Cache Init Error: {e}")

    def get(self, key: str) -> Optional[Dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT value, expiry FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    value, expiry = row
                    if expiry > time.time():
                        return json.loads(value)
                    else:
                        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any, ttl=86400): # Default 24h
        try:
            expiry = int(time.time() + ttl)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expiry) VALUES (?, ?, ?)",
                    (key, json.dumps(value), expiry)
                )
        except Exception:
            pass

# Initialize global cache
db_cache = SQLiteCache()

def _tmdb_get(path: str, params: Dict = None) -> Dict:
    """Helper for TMDb API calls with persistent caching."""
    cache_params = params.copy() if params else {}
    cache_key = f"tmdb:{path}:{json.dumps(cache_params, sort_keys=True)}"

    cached = db_cache.get(cache_key)
    if cached:
        return cached

    url = f"{TMDB_BASE}{path}"
    headers = {"accept": "application/json"}

    if TMDB_READ_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"

    merged_params = params.copy() if params else {}
    if not TMDB_READ_ACCESS_TOKEN:
        merged_params["api_key"] = TMDB_API_KEY

    try:
        response = _session.get(url, headers=headers, params=merged_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        db_cache.set(cache_key, data)
        return data
    except Exception as e:
        print(f"TMDb API Error: {e}")
        return {}

def _fetch_omdb_data(imdb_id: str) -> Dict:
    """Fetch extended info from OMDb with persistent caching."""
    if not imdb_id or not OMDB_API_KEY:
        return {}

    cache_key = f"omdb:{imdb_id}"
    cached = db_cache.get(cache_key)
    if cached:
        return cached

    params = {
        "apikey": OMDB_API_KEY,
        "i": imdb_id,
        "plot": "short"
    }

    try:
        response = _session.get(OMDB_BASE, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("Response") == "True":
            db_cache.set(cache_key, data)
            return data
        return {}
    except Exception:
        return {}

# --- Search Strategies ---

def _resolve_person_ids(names, job=None):
    person_ids = []
    for name in names:
        data = _tmdb_get("/search/person", {"query": name})
        results = data.get("results", [])
        if results:
            person_ids.append(results[0]["id"])
    return person_ids

def _resolve_keyword_ids(tags):
    keyword_ids = []
    for tag in tags:
        data = _tmdb_get("/search/keyword", {"query": tag})
        results = data.get("results", [])
        if results:
            keyword_ids.append(results[0]["id"])
    return keyword_ids

def _resolve_company_ids(names):
    company_ids = []
    for name in names:
        data = _tmdb_get("/search/company", {"query": name})
        results = data.get("results", [])
        if results:
            company_ids.append(results[0]["id"])
    return company_ids

def _find_movie_id_by_title(title):
    data = _tmdb_get("/search/movie", {"query": title, "page": 1})
    results = data.get("results", [])
    return results[0]["id"] if results else None

def _search_by_title(params):
    keywords = params.get("keywords", "")
    if not keywords: return []
    data = _tmdb_get("/search/movie", {"query": keywords, "page": 1})
    return data.get("results", [])[:10]

def _search_by_discover(params):
    genre_names = params.get("genres", [])
    genre_ids = [GENRE_MAP[g.lower()] for g in genre_names if g.lower() in GENRE_MAP]

    actor_names = params.get("actors", [])
    person_ids = _resolve_person_ids(actor_names)

    director_names = params.get("directors", [])
    director_ids = _resolve_person_ids(director_names)

    company_names = params.get("companies", [])
    company_ids = _resolve_company_ids(company_names)

    # NEW: Handle thematic keywords (e.g. "time travel", "dystopia")
    # We check both 'keywords' (if vague) and 'tmdb_keyword_tags' (if explicit)
    keyword_texts = params.get("tmdb_keyword_tags", [])
    if not keyword_texts and params.get("keywords") and "discover" in params.get("strategies", []):
         # If strategy is purely discover, use the generic keywords string as a tag source
         # But only if it's short/specific enough to likely be a tag
         if len(params["keywords"].split()) <= 3:
             keyword_texts.append(params["keywords"])
    
    keyword_ids = _resolve_keyword_ids(keyword_texts)

    discover_params = {
        "sort_by": params.get("sort_by", "popularity.desc"),
        "page": 1,
        "vote_count.gte": params.get("min_votes") or 50,
    }

    if genre_ids: discover_params["with_genres"] = ",".join(str(g) for g in genre_ids)
    if person_ids: discover_params["with_cast"] = "|".join(str(p) for p in person_ids)
    if director_ids: discover_params["with_crew"] = "|".join(str(d) for d in director_ids)
    if company_ids: discover_params["with_companies"] = "|".join(str(c) for c in company_ids)
    if keyword_ids: discover_params["with_keywords"] = "|".join(str(k) for k in keyword_ids)

    if params.get("year_from"): discover_params["primary_release_date.gte"] = f"{params['year_from']}-01-01"
    if params.get("year_to"): discover_params["primary_release_date.lte"] = f"{params['year_to']}-12-31"
    if params.get("min_rating"): discover_params["vote_average.gte"] = params["min_rating"]
    if params.get("runtime_min"): discover_params["with_runtime.gte"] = params["runtime_min"]
    if params.get("runtime_max"): discover_params["with_runtime.lte"] = params["runtime_max"]

    data = _tmdb_get("/discover/movie", discover_params)
    return data.get("results", [])[:10]

def _search_similar(params):
    title = params.get("similar_to_title") or params.get("keywords", "")
    if not title: return []
    movie_id = _find_movie_id_by_title(title)
    if not movie_id: return []
    data = _tmdb_get(f"/movie/{movie_id}/recommendations", {"page": 1})
    return data.get("results", [])[:10]

def search_movies(params: Dict) -> List[Dict]:
    """Orchestrate search using multiple strategies."""
    strategies = params.get("strategies", ["title_search"])
    all_results = []
    seen_ids = set()

    for strategy in strategies:
        try:
            if strategy == "title_search": results = _search_by_title(params)
            elif strategy == "discover": results = _search_by_discover(params)
            elif strategy == "similar": results = _search_similar(params)
            elif strategy == "multi_search":
                results = _search_by_discover(params)
                if len(results) < 5: results += _search_by_title(params)
            else: results = _search_by_title(params)

            for m in results:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_results.append(m)
        except Exception:
            continue

    return all_results[:10]


def _enrich_single_movie(m: Dict) -> Optional[Dict]:
    """Enrich a single movie with TMDb details + OMDb data. Used in parallel."""
    tmdb_id = m.get("id") or m.get("tmdb_id")
    if not tmdb_id:
        return None

    full_tmdb = get_movie_details(tmdb_id)
    if not full_tmdb:
        full_tmdb = m

    imdb_id = full_tmdb.get("imdb_id")
    omdb = _fetch_omdb_data(imdb_id) if imdb_id else None
    full_tmdb["_omdb"] = omdb
    return full_tmdb


def enrich_movie_data(movies: List[Dict]) -> List[Dict]:
    """Enriches a list of raw TMDb results with full details and OMDb data.
    Uses ThreadPoolExecutor for parallel API calls — massive speed boost."""
    enriched_results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {
            executor.submit(_enrich_single_movie, m): i
            for i, m in enumerate(movies)
        }
        # Collect results preserving original order
        results_by_idx = {}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                if result:
                    results_by_idx[idx] = result
            except Exception:
                pass

        for i in range(len(movies)):
            if i in results_by_idx:
                enriched_results.append(results_by_idx[i])

    return enriched_results


def format_movie_light(m: Dict) -> Dict:
    """Lightweight formatting for discover/trending — no OMDb call needed."""
    return {
        "tmdb_id": m.get("id"),
        "title": m.get("title"),
        "year": m.get("release_date", "")[:4] if m.get("release_date") else "N/A",
        "overview": m.get("overview"),
        "poster_url": f"{TMDB_IMAGE_BASE}{m.get('poster_path')}" if m.get("poster_path") else None,
        "backdrop_url": f"{TMDB_IMAGE_BASE}{m.get('backdrop_path')}" if m.get("backdrop_path") else None,
        "tmdb_rating": m.get("vote_average"),
        "genres": ", ".join(str(gid) for gid in m.get("genre_ids", [])) if m.get("genre_ids") else None,
    }


def get_movie_details(tmdb_id: int) -> Optional[Dict]:
    """Fetch full movie details from TMDb."""
    tmdb = _tmdb_get(f"/movie/{tmdb_id}", {"append_to_response": "credits,watch/providers,keywords"})
    return tmdb if tmdb else None

def format_movie_result(tmdb: Dict) -> Dict:
    """Merge TMDb and OMDb data with ROI analysis."""
    omdb = tmdb.get("_omdb") or {}

    # Financials
    budget_raw = tmdb.get("budget", 0)
    revenue_raw = tmdb.get("revenue", 0)

    budget_str = f"${budget_raw/1e6:.1f}M" if budget_raw >= 1e6 else "N/A"
    revenue_str = f"${revenue_raw/1e6:.1f}M" if revenue_raw >= 1e6 else "N/A"

    # ROI Calculation
    roi_str = "N/A"
    perf = "Unknown"
    perf_color = "slate"

    if budget_raw > 0 and revenue_raw > 0:
        multiplier = revenue_raw / budget_raw
        roi_str = f"{multiplier:.1f}x"

        if multiplier > 5.0:
            perf = "Blockbuster"
            perf_color = "emerald"
        elif multiplier > 2.5:
            perf = "Hit"
            perf_color = "indigo"
        elif multiplier > 1.5:
            perf = "Underperformer"
            perf_color = "amber"
        else:
            perf = "Flop"
            perf_color = "red"

    # Streaming Check
    providers = tmdb.get("watch/providers", {}).get("results", {}).get("US", {})
    flatrate = [p["provider_name"] for p in providers.get("flatrate", [])]
    streaming = ", ".join(flatrate) if flatrate else None

    # OMDb Ratings
    rt_score = "N/A"
    for rating in omdb.get("Ratings", []):
        if rating["Source"] == "Rotten Tomatoes":
            rt_score = rating["Value"]

    return {
        "tmdb_id": tmdb.get("id"),
        "title": tmdb.get("title"),
        "year": tmdb.get("release_date", "")[:4] if tmdb.get("release_date") else "N/A",
        "overview": tmdb.get("overview"),
        "tagline": tmdb.get("tagline"),
        "poster_url": f"{TMDB_IMAGE_BASE}{tmdb.get('poster_path')}" if tmdb.get("poster_path") else None,
        "backdrop_url": f"{TMDB_IMAGE_BASE}{tmdb.get('backdrop_path')}" if tmdb.get("backdrop_path") else None,
        "tmdb_rating": tmdb.get("vote_average"),
        "imdb_rating": omdb.get("imdbRating"),
        "rotten_tomatoes": rt_score,
        "metascore": omdb.get("Metascore"),
        "rated": omdb.get("Rated"),
        "director": omdb.get("Director") or ", ".join([c["name"] for c in tmdb.get("credits", {}).get("crew", []) if c.get("job") == "Director"]),
        "writers": omdb.get("Writer"),
        "actors": omdb.get("Actors") or ", ".join([c["name"] for c in tmdb.get("credits", {}).get("cast", [])[:5]]),
        "genres": ", ".join([g["name"] for g in tmdb.get("genres", [])]) if tmdb.get("genres") else None,
        "budget": budget_str,
        "revenue": revenue_str,
        "roi": roi_str,
        "performance": perf,
        "performance_color": perf_color,
        "runtime": tmdb.get("runtime"),
        "keywords": ", ".join([k["name"] for k in tmdb.get("keywords", {}).get("keywords", [])[:5]]),
        "production_countries": ", ".join([c["name"] for c in tmdb.get("production_countries", [])]),
        "spoken_languages": ", ".join([l["english_name"] for l in tmdb.get("spoken_languages", [])]),
        "streaming": streaming
    }

def get_trending_movies() -> List[Dict]:
    data = _tmdb_get("/trending/movie/day")
    return data.get("results", [])[:20] if data else []

def get_upcoming_movies() -> List[Dict]:
    data = _tmdb_get("/movie/upcoming")
    return data.get("results", [])[:20] if data else []

def get_now_playing() -> List[Dict]:
    data = _tmdb_get("/movie/now_playing")
    return data.get("results", [])[:20] if data else []

def get_top_rated() -> List[Dict]:
    data = _tmdb_get("/movie/top_rated")
    return data.get("results", [])[:20] if data else []

def get_movies_by_company(company_id: int) -> List[Dict]:
    data = _tmdb_get("/discover/movie", {
        "with_companies": str(company_id),
        "sort_by": "popularity.desc",
        "vote_count.gte": 100,
        "page": 1,
    })
    return data.get("results", [])[:20] if data else []

def get_movies_by_genre(genre_id: int) -> List[Dict]:
    data = _tmdb_get("/discover/movie", {
        "with_genres": str(genre_id),
        "sort_by": "popularity.desc",
        "vote_count.gte": 100,
        "page": 1,
    })
    return data.get("results", [])[:20] if data else []
