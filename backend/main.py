from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from backend.ai_engine import extract_search_params, rank_and_explain
from backend.movie_api import (
    search_movies, enrich_movie_data, format_movie_result, format_movie_light,
    get_trending_movies, get_upcoming_movies, get_now_playing, get_top_rated,
    get_movies_by_genre, get_movies_by_company, get_movie_details
)

app = FastAPI(title="Movie Oracle", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str

class MovieResult(BaseModel):
    tmdb_id: int | None = None
    title: str
    year: str | None = None
    overview: str | None = None
    tagline: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    tmdb_rating: float | None = None
    imdb_rating: str | None = None
    rotten_tomatoes: str | None = None
    metascore: str | None = None
    rated: str | None = None
    director: str | None = None
    writers: str | None = None
    actors: str | None = None
    genres: str | None = None
    budget: str | None = None
    revenue: str | None = None
    runtime: int | None = None
    keywords: str | None = None
    production_countries: str | None = None
    spoken_languages: str | None = None
    streaming: str | None = None
    roi: str | None = None
    performance: str | None = None
    performance_color: str | None = None
    relevance_explanation: str | None = None
    ai_score: int | None = None  # New field for Smart Oracle Score

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

    try:
        params = extract_search_params(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    ai_interpretation = params.get("explanation", "Searching for movies...")

    try:
        raw_movies = search_movies(params)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Movie search error: {str(e)}")

    if not raw_movies:
        return SearchResponse(
            query=query,
            ai_interpretation=ai_interpretation,
            summary="No movies found matching your query.",
            results=[],
        )

    enriched = enrich_movie_data(raw_movies)
    formatted = [format_movie_result(m) for m in enriched]

    try:
        ranking = rank_and_explain(query, formatted)
    except Exception:
        ranking = {"summary": "Results found:", "ranked_movies": []}

    # Merge ranking data (rank, explanation, SCORE)
    ranked_movies = ranking.get("ranked_movies", [])
    rank_map = {r["tmdb_id"]: r for r in ranked_movies if isinstance(r, dict) and "tmdb_id" in r}

    for movie in formatted:
        movie_id = movie.get("tmdb_id")
        rank_info = rank_map.get(movie_id, {})
        movie["relevance_explanation"] = rank_info.get("relevance_explanation", "")
        movie["ai_score"] = rank_info.get("score") # Map the new score

    # Sort
    ranked_ids = [r.get("tmdb_id") for r in ranked_movies if isinstance(r, dict)]
    formatted.sort(key=lambda m: ranked_ids.index(m.get("tmdb_id")) if m.get("tmdb_id") in ranked_ids else 999)

    return SearchResponse(
        query=query,
        ai_interpretation=ai_interpretation,
        summary=ranking.get("summary", "Here are your results:"),
        results=[MovieResult(**m) for m in formatted],
    )

@app.get("/api/details/{tmdb_id}", response_model=MovieResult)
def get_details(tmdb_id: int):
    movie = get_movie_details(tmdb_id)
    if not movie: raise HTTPException(status_code=404, detail="Movie not found")
    enriched = enrich_movie_data([movie])
    return MovieResult(**format_movie_result(enriched[0]))

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
