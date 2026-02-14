# Movie Oracle | AI-Powered Cinematic Discovery

The **Movie Oracle** is a sophisticated full-stack application that blends high-performance movie search with a "Reasoning" layer powered by Large Language Models. It interprets natural language queries to provide deeply personalized and accurate film recommendations.

## 🧠 The Intelligence (AIs)
The application uses **Google Gemini 2.0 Flash** (via the **OpenRouter API**) as its core reasoning engine. It serves two distinct roles:

*   **The Interpreter (Parameter Extraction)**: Gemini parses natural language into structured JSON objects, extracting genres, people, thematic keywords, and financial constraints (budget/revenue).
*   **The Critic (Ranking & Synthesis)**: The AI evaluates a candidate list of movies, ranking them based on intent and providing a personalized explanation for why each match was chosen.

## 🌐 The Data (APIs)
The Oracle synthesizes data from two primary industry sources:

*   **TMDb (The Movie Database)**: 
    *   Powers the **Discovery Engine** (filtering by studios, cast, crew, and year).
    *   Provides primary imagery (Posters and High-res Backdrops).
    *   Handles **Keyword ID Resolution**, mapping thematic concepts (e.g., "cyberpunk") to specific database IDs.
*   **OMDb (Open Movie Database)**: 
    *   Acts as a secondary "Enrichment" layer.
    *   Provides critical reception data including **Rotten Tomatoes**, **Metascore**, and **IMDb** ratings.

## ⚙️ How It Works (The Workflow)

1.  **Frontend**: Captures queries and triggers a smooth **FLIP animation** to slide the search bar to the top, maintaining a 60fps premium experience.
2.  **Backend (FastAPI)**: 
    *   **AI Interpretation**: Triggers Gemini to build a "Search Strategy."
    *   **Elastic Searching**: Hits multiple TMDb endpoints simultaneously using Python's `ThreadPoolExecutor` for parallel processing.
    *   **Caching Layer**: Uses a local **SQLite database** to cache TMDb and OMDb results for near-instant repeat lookups.
    *   **AI Reasoning**: Sends the final candidates back to Gemini for a "Final Cut" ranking and qualitative evaluation.
3.  **The Result**: The UI renders a ranked list with AI-generated interpretations, ROI analysis, and full critical metrics.

## 🛠️ Technical Stack
*   **Frontend**: HTML5, Vanilla JavaScript (ES6+), CSS Grid/Flexbox, Tailwind CSS, Lucide Icons.
*   **Backend**: Python, FastAPI (High-performance ASGI), `requests` for API communication.
*   **Storage**: SQLite3 (Persistent Cache).
*   **Performance**: Threaded parallel API calls and hardware-accelerated CSS transitions.

## Local development & preview
- Start the backend dev server:
  - Run the VS Code task **Run Movie Oracle (dev)** (or from terminal: `.venv/bin/python -m uvicorn backend.main:app --reload --port 8000`).
- Open the app in VS Code's Simple Browser: press Cmd/Ctrl+Shift+P → `Simple Browser: Open` and enter `http://127.0.0.1:8000/`.
- The API health endpoint is at `http://127.0.0.1:8000/api/health`.

This lets you edit files and preview changes instantly in a mini browser pane inside VS Code.
