import os
import requests
import json

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


from backend.cache import db_cache


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

def _get_person_imdb_url(tmdb_person_id: int) -> Optional[str]:
    """Fetch a person's IMDb URL from their TMDb ID."""
    data = _tmdb_get(f"/person/{tmdb_person_id}", {})
    imdb_id = data.get("imdb_id")
    return f"https://www.imdb.com/name/{imdb_id}/" if imdb_id else None


def _resolve_people_links(people: List[Dict]) -> List[Dict]:
    """Resolve IMDb URLs for a list of crew/cast members in parallel."""
    if not people:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_get_person_imdb_url, p["id"]): p
            for p in people if p.get("id")
        }
        for future in as_completed(futures):
            person = futures[future]
            try:
                imdb_url = future.result()
            except Exception:
                imdb_url = None
            results.append({"name": person["name"], "imdb_url": imdb_url})
    # Preserve original order
    name_order = [p["name"] for p in people]
    results.sort(key=lambda r: name_order.index(r["name"]) if r["name"] in name_order else 999)
    return results


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
    seen = set()
    for tag in tags:
        # Try the tag as-is first, then fall back to variations
        variations = [tag]
        if "-" in tag:
            # "cult-film" -> "cult film" -> "cult"
            variations.append(tag.replace("-", " "))
            variations.extend(tag.split("-"))
        for variant in variations:
            data = _tmdb_get("/search/keyword", {"query": variant})
            results = data.get("results", [])
            if results:
                kid = results[0]["id"]
                if kid not in seen:
                    seen.add(kid)
                    keyword_ids.append(kid)
                break  # Found a match for this tag, move to next
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
    director_names = params.get("directors", [])
    company_names = params.get("companies", [])

    # Handle thematic keywords
    keyword_texts = params.get("tmdb_keyword_tags", [])
    if not keyword_texts and params.get("keywords") and "discover" in params.get("strategies", []):
        if len(params["keywords"].split()) <= 3:
            keyword_texts.append(params["keywords"])

    # Parallel ID resolution for all entity types
    person_ids = []
    director_ids = []
    company_ids = []
    keyword_ids = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        if actor_names:
            futures['actors'] = executor.submit(_resolve_person_ids, actor_names)
        if director_names:
            futures['directors'] = executor.submit(_resolve_person_ids, director_names)
        if company_names:
            futures['companies'] = executor.submit(_resolve_company_ids, company_names)
        if keyword_texts:
            futures['keywords'] = executor.submit(_resolve_keyword_ids, keyword_texts)
        
        for key, future in futures.items():
            try:
                result = future.result(timeout=5)
                if key == 'actors':
                    person_ids = result
                elif key == 'directors':
                    director_ids = result
                elif key == 'companies':
                    company_ids = result
                elif key == 'keywords':
                    keyword_ids = result
            except Exception:
                pass

    discover_params = {
        "sort_by": params.get("sort_by", "popularity.desc"),
        "page": 1,
        "vote_count.gte": params.get("min_votes") or 50,
    }

    # Use OR (|) for 3+ genres so movies don't need ALL genres at once
    if genre_ids:
        sep = "|" if len(genre_ids) >= 3 else ","
        discover_params["with_genres"] = sep.join(str(g) for g in genre_ids)
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

def _discover_relaxed(params: Dict) -> List[Dict]:
    """Try discover with progressively relaxed constraints until enough results appear."""
    MIN_RESULTS = 5

    # Attempt 1: Full params as-is
    results = _search_by_discover(params)
    if len(results) >= MIN_RESULTS:
        return results

    # Attempt 2: Drop keywords (they're often the most restrictive filter)
    if params.get("tmdb_keyword_tags"):
        relaxed = {**params, "tmdb_keyword_tags": []}
        relaxed_results = _search_by_discover(relaxed)
        if len(relaxed_results) >= MIN_RESULTS:
            print("Relaxed: dropped keywords")
            return relaxed_results
        # Keep whichever gave more
        if len(relaxed_results) > len(results):
            results = relaxed_results

    # Attempt 3: Drop keywords + loosen rating/votes
    if len(results) < MIN_RESULTS:
        relaxed = {**params, "tmdb_keyword_tags": [], "min_rating": None, "min_votes": 50}
        relaxed_results = _search_by_discover(relaxed)
        if len(relaxed_results) > len(results):
            print("Relaxed: dropped keywords + loosened filters")
            results = relaxed_results

    return results


def search_movies(params: Dict) -> List[Dict]:
    """Orchestrate search using multiple strategies with automatic fallback."""
    strategies = params.get("strategies", ["discover"])
    all_results = []
    seen_ids = set()

    for strategy in strategies:
        try:
            if strategy == "title_search": results = _search_by_title(params)
            elif strategy == "discover": results = _discover_relaxed(params)
            elif strategy == "similar": results = _search_similar(params)
            elif strategy == "multi_search":
                results = _discover_relaxed(params)
                if len(results) < 5: results += _search_by_title(params)
            else: results = _discover_relaxed(params)

            for m in results:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_results.append(m)
        except Exception as e:
            print(f"Strategy {strategy} failed: {e}")
            continue

    # FALLBACK: If discover returned nothing, try title search
    if not all_results and "discover" in strategies and params.get("keywords"):
        try:
            results = _search_by_title(params)
            for m in results:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_results.append(m)
        except Exception:
            pass

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

    # Watch Providers (structured)
    providers = tmdb.get("watch/providers", {}).get("results", {}).get("US", {})
    LOGO_BASE = "https://image.tmdb.org/t/p/original"

    def _fmt_providers(plist):
        return [{"name": p["provider_name"], "logo_url": f"{LOGO_BASE}{p['logo_path']}"} for p in plist if p.get("logo_path")]

    flatrate = providers.get("flatrate", [])
    streaming = ", ".join(p["provider_name"] for p in flatrate) if flatrate else None
    watch_providers = None
    if providers:
        watch_providers = {
            "link": providers.get("link"),
            "flatrate": _fmt_providers(flatrate),
            "rent": _fmt_providers(providers.get("rent", [])),
            "buy": _fmt_providers(providers.get("buy", [])),
        }

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
        "director_links": _resolve_people_links([c for c in tmdb.get("credits", {}).get("crew", []) if c.get("job") == "Director"]),
        "actor_links": _resolve_people_links(tmdb.get("credits", {}).get("cast", [])[:5]),
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
        "streaming": streaming,
        "watch_providers": watch_providers,
        "budget_raw": budget_raw,
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
