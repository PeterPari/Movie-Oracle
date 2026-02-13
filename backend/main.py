from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from backend.ai_engine import extract_search_params, rank_and_explain
from backend.movie_api import (
    search_movies, enrich_movie_data, format_movie_result, format_movie_light,
    get_trending_movies, get_upcoming_movies, get_now_playing, get_top_rated,
    get_movies_by_genre, get_movies_by_company, get_movie_details
)
from backend.cache import db_cache

app = FastAPI(title="Movie Oracle", version="2.1.0")

# Clear stale Gemini cache on startup (model was upgraded)
from backend.cache import db_cache as _cache
_cache.clear_prefix("gemini:")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    """Quick health check for cold-start detection."""
    return {"status": "ok"}

@app.get("/api/ready")
def readiness_check():
    return {"status": "ready"}


class SearchRequest(BaseModel):
    query: str

class PersonLink(BaseModel):
    name: str
    imdb_url: Optional[str] = None

class WatchProviderItem(BaseModel):
    name: str
    logo_url: Optional[str] = None

class WatchProviders(BaseModel):
    link: Optional[str] = None
    flatrate: List[WatchProviderItem] = Field(default_factory=list)
    rent: List[WatchProviderItem] = Field(default_factory=list)
    buy: List[WatchProviderItem] = Field(default_factory=list)

class MovieResult(BaseModel):
    tmdb_id: Optional[int] = None
    title: str
    year: Optional[str] = None
    overview: Optional[str] = None
    tagline: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    tmdb_rating: Optional[float] = None
    imdb_rating: Optional[str] = None
    rotten_tomatoes: Optional[str] = None
    metascore: Optional[str] = None
    rated: Optional[str] = None
    director: Optional[str] = None
    writers: Optional[str] = None
    actors: Optional[str] = None
    director_links: Optional[List[PersonLink]] = None
    actor_links: Optional[List[PersonLink]] = None
    genres: Optional[str] = None
    budget: Optional[str] = None
    budget_raw: Optional[int] = None
    revenue: Optional[str] = None
    runtime: Optional[int] = None
    keywords: Optional[str] = None
    production_countries: Optional[str] = None
    spoken_languages: Optional[str] = None
    streaming: Optional[str] = None
    watch_providers: Optional[WatchProviders] = None
    roi: Optional[str] = None
    performance: Optional[str] = None
    performance_color: Optional[str] = None
    relevance_explanation: Optional[str] = None
    oracle_score: Optional[int] = None

class SearchResponse(BaseModel):
    query: str
    ai_interpretation: str
    summary: str
    results: list[MovieResult]

class TrendingResponse(BaseModel):
    trending: list[MovieResult]
    upcoming: list[MovieResult]

class DiscoverResponse(BaseModel):
    trending: list[MovieResult]
    now_playing: list[MovieResult]
    top_rated: list[MovieResult]
    upcoming: list[MovieResult]

@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    cache_key = f"search:{query.lower()}"
    cached = db_cache.get(cache_key)
    if cached:
        return cached

    start_time = time.perf_counter()

    try:
        params = extract_search_params(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    t_ai = time.perf_counter()

    ai_interpretation = params.get("explanation", "Searching for movies...")

    try:
        raw_movies = search_movies(params)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Movie search error: {str(e)}")

    t_search = time.perf_counter()

    # If TMDb returned nothing, provide a local demo fallback for dev (keeps Discover useful offline)
    if not raw_movies:
        from backend.movie_api import get_demo_light_results
        demo = get_demo_light_results(query)
        if demo:
            # Return demo results immediately (they are already in 'light' format)
            response = SearchResponse(
                query=query,
                ai_interpretation=ai_interpretation,
                summary="Demo results (TMDb unavailable or returned no matches)",
                results=[MovieResult(**m) for m in demo],
            )
            db_cache.set(cache_key, response.dict(), ttl=60)
            return response

        response = SearchResponse(
            query=query,
            ai_interpretation=ai_interpretation,
            summary="No movies found matching your query.",
            results=[],
        )
        db_cache.set(cache_key, response.dict(), ttl=600)
        return response

    enriched = enrich_movie_data(raw_movies)
    formatted = [format_movie_result(m, resolve_links=False) for m in enriched]

    t_enrich = time.perf_counter()

    # Budget post-filtering (TMDb discover doesn't support budget filters)
    min_budget = params.get("min_budget")
    max_budget = params.get("max_budget")
    if min_budget or max_budget:
        filtered = []
        for m in formatted:
            b = m.get("budget_raw", 0) or 0
            if min_budget and b < min_budget:
                continue
            if max_budget and b > max_budget:
                continue
            filtered.append(m)
        if filtered:
            formatted = filtered

    # Ranking with timeout (don't let it slow down the response)
    ranking = {"summary": "Here are your results:", "ranked_movies": []}
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(rank_and_explain, query, formatted)
            try:
                ranking = future.result(timeout=12)  # 12-second timeout for ranking
            except FuturesTimeoutError:
                print("Ranking timed out, returning without scores")
    except Exception as e:
        print(f"Ranking error: {e}")

    t_rank = time.perf_counter()

    # Merge ranking data (rank, explanation, SCORE)
    ranked_movies = ranking.get("ranked_movies", [])
    rank_map = {r["tmdb_id"]: r for r in ranked_movies if isinstance(r, dict) and "tmdb_id" in r}

    for movie in formatted:
        movie_id = movie.get("tmdb_id")
        rank_info = rank_map.get(movie_id, {})
        movie["relevance_explanation"] = rank_info.get("relevance_explanation", "")
        movie["oracle_score"] = rank_info.get("oracle_score", None)

    # Sort
    ranked_ids = [r.get("tmdb_id") for r in ranked_movies if isinstance(r, dict)]
    formatted.sort(key=lambda m: ranked_ids.index(m.get("tmdb_id")) if m.get("tmdb_id") in ranked_ids else 999)

    response = SearchResponse(
        query=query,
        ai_interpretation=ai_interpretation,
        summary=ranking.get("summary", "Here are your results:"),
        results=[MovieResult(**m) for m in formatted],
    )
    db_cache.set(cache_key, response.dict(), ttl=600)
    total = time.perf_counter() - start_time
    print(
        f"Search timings: ai={t_ai-start_time:.2f}s search={t_search-t_ai:.2f}s "
        f"enrich={t_enrich-t_search:.2f}s rank={t_rank-t_enrich:.2f}s total={total:.2f}s"
    )
    return response

@app.get("/api/details/{tmdb_id}", response_model=MovieResult)
def get_details(tmdb_id: int):
    movie = get_movie_details(tmdb_id)
    if not movie: raise HTTPException(status_code=404, detail="Movie not found")
    enriched = enrich_movie_data([movie])
    return MovieResult(**format_movie_result(enriched[0], resolve_links=True))

@app.get("/api/trending", response_model=TrendingResponse)
def get_trending():
    t = get_trending_movies()
    u = get_upcoming_movies()
    return TrendingResponse(
        trending=[MovieResult(**format_movie_light(m)) for m in t],
        upcoming=[MovieResult(**format_movie_light(m)) for m in u]
    )

@app.get("/api/discover", response_model=DiscoverResponse)
def get_discover():
    with ThreadPoolExecutor(max_workers=4) as ex:
        f1, f2 = ex.submit(get_trending_movies), ex.submit(get_now_playing)
        f3, f4 = ex.submit(get_top_rated), ex.submit(get_upcoming_movies)
        return DiscoverResponse(
            trending=[MovieResult(**format_movie_light(m)) for m in f1.result()],
            now_playing=[MovieResult(**format_movie_light(m)) for m in f2.result()],
            top_rated=[MovieResult(**format_movie_light(m)) for m in f3.result()],
            upcoming=[MovieResult(**format_movie_light(m)) for m in f4.result()]
        )

@app.get("/api/genre/{genre_id}")
def get_genre(genre_id: int):
    return {"results": [MovieResult(**format_movie_light(m)) for m in get_movies_by_genre(genre_id)]}

@app.get("/api/company/{company_id}")
def get_company(company_id: int):
    return {"results": [MovieResult(**format_movie_light(m)) for m in get_movies_by_company(company_id)]}

FRONTEND_DIR = Path(__file__).parent.parent
@app.get("/")
def serve_index(): return FileResponse(FRONTEND_DIR / "index.html")
@app.get("/discover")
def serve_discover(): return FileResponse(FRONTEND_DIR / "discover.html")
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
@app.get("/app.js")
def serve_app_js(): return FileResponse(FRONTEND_DIR / "app.js")
@app.get("/discover.js")
def serve_discover_js(): return FileResponse(FRONTEND_DIR / "discover.js")
@app.get("/shared.js")
def serve_shared_js(): return FileResponse(FRONTEND_DIR / "shared.js")
