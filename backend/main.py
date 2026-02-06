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
    search_movies,
    enrich_movie_data,
    format_movie_result,
    format_movie_light,
    get_trending_movies,
    get_upcoming_movies,
    get_now_playing,
    get_top_rated,
    get_movies_by_genre,
    get_movies_by_company,
    get_movie_details,
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

    # Step 1: AI extracts search parameters
    try:
        params = extract_search_params(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    ai_interpretation = params.get("explanation", "Searching for movies...")

    # Step 2: Search TMDb using multi-strategy approach
    try:
        raw_movies = search_movies(params)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Movie search error: {str(e)}")

    if not raw_movies:
        return SearchResponse(
            query=query,
            ai_interpretation=ai_interpretation,
            summary="No movies found matching your query. Try rephrasing your search.",
            results=[],
        )

    # Step 3: Enrich with TMDb details + OMDb data (now parallelized!)
    enriched = enrich_movie_data(raw_movies)
    formatted = [format_movie_result(m) for m in enriched]

    # Step 4: AI ranks and explains results
    try:
        ranking = rank_and_explain(query, formatted)
    except Exception:
        ranking = {
            "summary": "Here are the movies I found:",
            "ranked_movies": [
                {
                    "tmdb_id": m["tmdb_id"],
                    "rank": i + 1,
                    "relevance_explanation": "",
                }
                for i, m in enumerate(formatted)
            ],
        }

    # Step 5: Merge ranking data into results
    ranked_movies = ranking.get("ranked_movies", [])
    rank_map = {}
    for r in ranked_movies:
        if isinstance(r, dict) and "tmdb_id" in r:
            rank_map[r["tmdb_id"]] = r

    for movie in formatted:
        movie_id = movie.get("tmdb_id")
        rank_info = rank_map.get(movie_id, {})
        movie["relevance_explanation"] = rank_info.get("relevance_explanation", "")

    # Sort by AI ranking order
    ranked_ids = [r.get("tmdb_id") for r in ranked_movies if isinstance(r, dict)]
    formatted.sort(
        key=lambda m: ranked_ids.index(m.get("tmdb_id"))
        if m.get("tmdb_id") in ranked_ids
        else 999
    )

    return SearchResponse(
        query=query,
        ai_interpretation=ai_interpretation,
        summary=ranking.get("summary", "Here are your results:"),
        results=[MovieResult(**m) for m in formatted],
    )

@app.get("/api/details/{tmdb_id}", response_model=MovieResult)
def get_details(tmdb_id: int):
    try:
        movie = get_movie_details(tmdb_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")

        enriched = enrich_movie_data([movie])
        formatted = format_movie_result(enriched[0])
        return MovieResult(**formatted)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching details: {str(e)}")


@app.get("/api/trending", response_model=TrendingResponse)
def get_trending():
    """Fast trending endpoint — uses lightweight formatting, no OMDb calls."""
    try:
        trending_raw = get_trending_movies()
        upcoming_raw = get_upcoming_movies()

        trending_formatted = [format_movie_light(m) for m in trending_raw]
        upcoming_formatted = [format_movie_light(m) for m in upcoming_raw]

        return TrendingResponse(
            trending=[MovieResult(**m) for m in trending_formatted],
            upcoming=[MovieResult(**m) for m in upcoming_formatted],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching trending: {str(e)}")


@app.get("/api/discover", response_model=DiscoverResponse)
def get_discover():
    """Fast discover endpoint — fetches all sections in parallel, lightweight format."""
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            f_trending = executor.submit(get_trending_movies)
            f_now_playing = executor.submit(get_now_playing)
            f_top_rated = executor.submit(get_top_rated)
            f_upcoming = executor.submit(get_upcoming_movies)

            trending_raw = f_trending.result()
            now_playing_raw = f_now_playing.result()
            top_rated_raw = f_top_rated.result()
            upcoming_raw = f_upcoming.result()

        return DiscoverResponse(
            trending=[MovieResult(**format_movie_light(m)) for m in trending_raw],
            now_playing=[MovieResult(**format_movie_light(m)) for m in now_playing_raw],
            top_rated=[MovieResult(**format_movie_light(m)) for m in top_rated_raw],
            upcoming=[MovieResult(**format_movie_light(m)) for m in upcoming_raw],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching discover: {str(e)}")


@app.get("/api/genre/{genre_id}")
def get_genre_movies(genre_id: int):
    """Fetch movies by genre — lightweight format."""
    try:
        raw = get_movies_by_genre(genre_id)
        formatted = [format_movie_light(m) for m in raw]
        return {"results": [MovieResult(**m) for m in formatted]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching genre: {str(e)}")


@app.get("/api/company/{company_id}")
def get_company_movies(company_id: int):
    """Fetch movies by company — lightweight format."""
    try:
        raw = get_movies_by_company(company_id)
        formatted = [format_movie_light(m) for m in raw]
        return {"results": [MovieResult(**m) for m in formatted]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching company: {str(e)}")


# --- Static File Serving ---

FRONTEND_DIR = Path(__file__).parent.parent


@app.get("/")
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/discover")
def serve_discover():
    return FileResponse(FRONTEND_DIR / "discover.html")


app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/app.js")
def serve_app_js():
    return FileResponse(FRONTEND_DIR / "app.js")


@app.get("/discover.js")
def serve_discover_js():
    return FileResponse(FRONTEND_DIR / "discover.js")


if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.getenv("PORT", 8080))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
