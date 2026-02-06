import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

MOCK_AI_PARAMS = {
    "strategies": ["title_search"],
    "keywords": "inception",
    "tmdb_keyword_tags": [],
    "genres": ["science fiction", "thriller"],
    "exclude_genres": [],
    "actors": [],
    "directors": [],
    "crew": [],
    "year_from": None,
    "year_to": None,
    "min_rating": None,
    "max_rating": None,
    "min_votes": None,
    "sort_by": "popularity.desc",
    "language": None,
    "region": None,
    "similar_to_title": None,
    "runtime_min": None,
    "runtime_max": None,
    "include_adult": False,
    "explanation": "Looking for the movie Inception",
}

MOCK_TMDB_RESULTS = [
    {
        "id": 27205,
        "title": "Inception",
        "release_date": "2010-07-16",
        "overview": "A thief who steals corporate secrets through dream-sharing technology.",
        "poster_path": "/9gk7adHYeDvHkCSEhnivolU8768.jpg",
        "backdrop_path": "/s3TBrRGB1iav7gFOCNx3H31MoES.jpg",
        "vote_average": 8.4,
        "genre_ids": [28, 878, 12],
        "popularity": 95.3,
    },
]

MOCK_ENRICHED = [
    {
        "id": 27205,
        "title": "Inception",
        "release_date": "2010-07-16",
        "overview": "A thief who steals corporate secrets through dream-sharing technology.",
        "poster_path": "/9gk7adHYeDvHkCSEhnivolU8768.jpg",
        "backdrop_path": "/s3TBrRGB1iav7gFOCNx3H31MoES.jpg",
        "vote_average": 8.4,
        "genre_ids": [28, 878, 12],
        "popularity": 95.3,
        "budget": 160000000,
        "revenue": 836836967,
        "runtime": 148,
        "tagline": "Your mind is the scene of the crime.",
        "imdb_id": "tt1375666",
        "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
        "credits": {
            "cast": [{"name": "Leonardo DiCaprio"}, {"name": "Joseph Gordon-Levitt"}],
            "crew": [{"name": "Christopher Nolan", "job": "Director", "department": "Directing"}],
        },
        "keywords": {"keywords": [{"name": "dream"}, {"name": "heist"}]},
        "production_countries": [{"name": "United States of America"}],
        "spoken_languages": [{"english_name": "English"}],
        "_omdb": {
            "imdbRating": "8.8",
            "Metascore": "74",
            "Rated": "PG-13",
            "Director": "Christopher Nolan",
            "Actors": "Leonardo DiCaprio, Joseph Gordon-Levitt",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "87%"}],
        },
        "roi": "5.2x",
        "performance": "Blockbuster"
    },
]

MOCK_RANKING = {
    "summary": "Inception is a perfect match for your query.",
    "ranked_movies": [
        {
            "tmdb_id": 27205,
            "rank": 1,
            "relevance_explanation": "The original Inception film, a sci-fi masterpiece.",
        },
    ],
}


@patch("backend.main.rank_and_explain", return_value=MOCK_RANKING)
@patch("backend.main.enrich_movie_data", return_value=MOCK_ENRICHED)
@patch("backend.main.search_movies", return_value=MOCK_TMDB_RESULTS)
@patch("backend.main.extract_search_params", return_value=MOCK_AI_PARAMS)
def test_search_success(mock_extract, mock_search, mock_enrich, mock_rank):
    response = client.post("/api/search", json={"query": "inception"})
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "inception"
    assert data["ai_interpretation"] == "Looking for the movie Inception"
    assert len(data["results"]) == 1
    movie = data["results"][0]
    assert movie["title"] == "Inception"
    assert movie["budget"] == "$160.0M"
    assert movie["revenue"] == "$836.8M"
    assert movie["runtime"] == 148
    assert movie["director"] == "Christopher Nolan"
    assert movie["imdb_rating"] == "8.8"
    assert movie["rotten_tomatoes"] == "87%"
    assert movie["keywords"] == "dream, heist"
    assert movie["roi"] == "5.2x"
    assert movie["performance"] == "Blockbuster"
    assert movie["streaming"] is None


def test_search_empty_query():
    response = client.post("/api/search", json={"query": ""})
    assert response.status_code == 400


def test_search_missing_query():
    response = client.post("/api/search", json={})
    assert response.status_code == 422


@patch("backend.main.extract_search_params", return_value=MOCK_AI_PARAMS)
@patch("backend.main.search_movies", return_value=[])
def test_search_no_results(mock_search, mock_extract):
    response = client.post("/api/search", json={"query": "some obscure movie"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 0
    assert "No movies found" in data["summary"]


@patch("backend.main.extract_search_params", side_effect=RuntimeError("AI down"))
def test_search_ai_failure(mock_extract):
    response = client.post("/api/search", json={"query": "inception"})
    assert response.status_code == 502
    assert "AI service error" in response.json()["detail"]


@patch("backend.main.rank_and_explain", side_effect=RuntimeError("Ranking failed"))
@patch("backend.main.enrich_movie_data", return_value=MOCK_ENRICHED)
@patch("backend.main.search_movies", return_value=MOCK_TMDB_RESULTS)
@patch("backend.main.extract_search_params", return_value=MOCK_AI_PARAMS)
def test_search_ranking_failure_graceful(mock_extract, mock_search, mock_enrich, mock_rank):
    response = client.post("/api/search", json={"query": "inception"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["summary"] == "Here are the movies I found:"


@patch("backend.main.enrich_movie_data", return_value=MOCK_ENRICHED)
@patch("backend.main.get_upcoming_movies", return_value=MOCK_TMDB_RESULTS)
@patch("backend.main.get_trending_movies", return_value=MOCK_TMDB_RESULTS)
def test_get_trending(mock_trending, mock_upcoming, mock_enrich):
    response = client.get("/api/trending")
    assert response.status_code == 200
    data = response.json()
    assert "trending" in data
    assert "upcoming" in data
    assert len(data["trending"]) == 1
    assert data["trending"][0]["title"] == "Inception"


def test_index_page_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_static_js_served():
    response = client.get("/frontend/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_root_app_js_served():
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_root_discover_js_served():
    response = client.get("/discover.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]

