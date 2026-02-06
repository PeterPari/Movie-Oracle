import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)


GENRE_MAP = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "science fiction": 878,
    "sci-fi": 878,
    "tv movie": 10770,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

EXTRACT_SYSTEM_PROMPT = """You are an advanced movie search AI. Given ANY natural language query about movies, you must interpret the user's intent and produce structured search parameters. You can handle virtually any kind of movie question.

You MUST return ONLY valid JSON. No markdown, no explanation outside the JSON.

## Query Types You Handle:
- Specific titles: "Inception", "that movie with the spinning top"
- By characteristics: "90s action movies", "dark psychological thrillers"
- By people: actors, directors, composers, writers — "directed by Denis Villeneuve", "starring Meryl Streep"
- By mood/theme: "feel-good movies", "movies about grief", "mind-bending plots"
- By comparison: "movies like Interstellar", "similar to The Shawshank Redemption"
- By awards: "Oscar winners for best picture", "critically acclaimed 2023 films"
- By budget/revenue: "highest grossing movies", "low budget horror hits"
- By region/language: "Korean thrillers", "French romantic comedies", "Bollywood action"
- By time period depicted: "movies set in medieval times", "movies set in the future"
- By production details: "movies filmed in New York", "Netflix originals"
- By audience: "family-friendly adventure", "date night movies"
- Trivia/facts: "longest movies ever made", "movies with surprise twist endings"
- Combined complex queries: "low budget horror hits starring unknown actors"

## Search Strategies (pick one or more):
1. "title_search" — User wants a specific movie by name
2. "discover" — Filter by genre, year, rating, cast, crew, keywords, language, region
3. "keyword_search" — Search TMDb keyword tags (themes like "time-travel", "heist", "low-budget", "independent-film")
4. "similar" — Find movies similar to a reference movie
5. "multi_search" — Run multiple searches and combine results

## Genre list (use exact names):
action, adventure, animation, comedy, crime, documentary, drama, family, fantasy, history, horror, music, mystery, romance, science fiction, thriller, war, western

## Language codes (common): en, ko, ja, fr, es, de, it, hi, zh, pt, ru, sv, da, nl, pl, tr

## Return this JSON structure:
{
  "strategies": ["discover"],
  "keywords": "fallback text search terms",
  "tmdb_keyword_tags": ["low-budget", "independent-film"],
  "genres": ["horror"],
  "exclude_genres": [],
  "companies": ["Marvel Studios", "A24"],
  "actors": ["actor names"],
  "directors": ["director names"],
  "crew": ["other crew member names"],
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
- "strategies" is an array. Use ["title_search"] for specific titles. Use ["discover", "keyword_search"] for thematic queries. Use ["similar"] when user says "like X" or "similar to X". Use ["multi_search"] for very complex queries.
- "companies" should contain production company names if mentioned (e.g. "Disney", "Marvel", "A24", "Warner Bros", "Lucasfilm").
- "tmdb_keyword_tags" matches thematic concepts to specific TMDb keywords. BE VERY SPECIFIC.
  - Examples: "time travel" -> ["time travel"], "dystopia" -> ["dystopia"], "heist" -> ["heist"], "revenge" -> ["revenge"], "twist ending" -> ["twist ending"], "space" -> ["space"], "zombies" -> ["zombie"], "serial killer" -> ["serial killer"], "underdog" -> ["underdog"], "high school" -> ["high school"], "magic" -> ["magic"], "robots" -> ["android", "robot"], "vampires" -> ["vampire"].
  - If user implies a theme (e.g. "mind bending"), use relevant keywords (e.g. ["psychological thriller", "mind fuck", "philosophy"]).
  - For "low budget", use ["independent film", "low budget"].
- "sort_by" options: popularity.desc, vote_average.desc, primary_release_date.desc, revenue.desc, vote_count.desc
- For "highest grossing", use sort_by: "revenue.desc"
- For "longest movies", use runtime_min: 180
- For "critically acclaimed", use min_rating: 7.5 and sort_by: "vote_average.desc" and min_votes: 500
- For foreign language queries, set "language" to the appropriate code
- Always fill in "explanation" with a natural language interpretation of the query. Explicitly mention if the user cares about budget or ROI.
- If the query is vague or abstract, do your best — pick relevant keyword tags and genres"""

RANK_SYSTEM_PROMPT = """You are an expert film critic and recommendation engine. Given the user's original query and a list of candidate movies with full details (ratings, budget, revenue, runtime, cast, crew, keywords, streaming info), rank and evaluate them.

You have deep knowledge of cinema. Use ALL available data to make intelligent rankings:
- **Strictly penalize** movies that do not match the core intent of the query. If the user asks for "Time Travel", a movie that just "feels like time travel" but isn't should be ranked low or excluded.
- **Commercial vs. Critical**: If user asks for "hits" or "blockbusters", prioritize ROI (Revenue/Budget) over critical acclaim. If they ask for "masterpieces" or "art", prioritize ratings (Metascore/Rotten Tomatoes).
- **Budget Realism**: If user asks for "low budget", prioritize actual low spend (<$10M), not just "indie feel".
- **Mention Status**: Explicitly label films as "Blockbuster", "Flop", "Cult Classic" in your explanation if relevant to the query.

Return ONLY valid JSON, no markdown:
{
  "summary": "2-3 sentence overall recommendation summary with personality and insight",
  "ranked_movies": [
    {
      "tmdb_id": 12345,
      "rank": 1,
      "relevance_explanation": "1-2 sentence explanation of why this matches, referencing specific data (ROI, Awards, Keywords)"
    }
  ]
}

Be opinionated and helpful. If some results don't match well, say so honestly. If the results are great matches, be enthusiastic."""


def _call_gemini(system_prompt, user_prompt, temperature=0.3):
    """Call Google Gemini API using official SDK"""
    # Combine system and user prompts
    combined_prompt = f"{system_prompt}\n\nUser Query: {user_prompt}"
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=combined_prompt,
        config={
            "temperature": temperature,
            "max_output_tokens": 2000,
        }
    )
    
    return response.text


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
        # Ensure required fields
        params.setdefault("strategies", ["title_search"])
        params.setdefault("keywords", query)
        params.setdefault("tmdb_keyword_tags", [])
        params.setdefault("genres", [])
        params.setdefault("exclude_genres", [])
        params.setdefault("companies", [])
        params.setdefault("actors", [])
        params.setdefault("directors", [])
        params.setdefault("crew", [])
        params.setdefault("year_from", None)
        params.setdefault("year_to", None)
        params.setdefault("min_rating", None)
        params.setdefault("max_rating", None)
        params.setdefault("min_votes", None)
        params.setdefault("sort_by", "popularity.desc")
        params.setdefault("language", None)
        params.setdefault("region", None)
        params.setdefault("similar_to_title", None)
        params.setdefault("runtime_min", None)
        params.setdefault("runtime_max", None)
        params.setdefault("include_adult", False)
        params.setdefault("explanation", "Searching for movies...")
        return params
    except (json.JSONDecodeError, KeyError, IndexError):
        return {
            "strategies": ["title_search"],
            "keywords": query,
            "tmdb_keyword_tags": [],
            "genres": [],
            "exclude_genres": [],
            "companies": [],
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
            "explanation": f"Searching for: {query}",
        }


def rank_and_explain(query, movies):
    movie_summaries = []
    for m in movies:
        summary = {
            "tmdb_id": m.get("tmdb_id"),
            "title": m.get("title"),
            "year": m.get("year"),
            "overview": m.get("overview", "")[:300],
            "tmdb_rating": m.get("tmdb_rating"),
            "imdb_rating": m.get("imdb_rating"),
            "rotten_tomatoes": m.get("rotten_tomatoes"),
            "metascore": m.get("metascore"),
            "director": m.get("director"),
            "actors": m.get("actors"),
            "budget": m.get("budget"),
            "revenue": m.get("revenue"),
            "runtime": m.get("runtime"),
            "keywords": m.get("keywords"),
            "production_countries": m.get("production_countries"),
            "spoken_languages": m.get("spoken_languages"),
            "tagline": m.get("tagline"),
        }
        movie_summaries.append(summary)

    user_content = (
        f"User query: {query}\n\n"
        f"Candidate movies:\n{json.dumps(movie_summaries, indent=2)}"
    )

    try:
        content = _call_gemini(RANK_SYSTEM_PROMPT, user_content, temperature=0.5)
        return _parse_json_response(content)
    except (json.JSONDecodeError, KeyError, IndexError):
        return {
            "summary": "Here are the movies I found:",
            "ranked_movies": [
                {
                    "tmdb_id": m.get("tmdb_id"),
                    "rank": i + 1,
                    "relevance_explanation": "",
                }
                for i, m in enumerate(movies)
            ],
        }
