# Shelf Aware

Analyze someone's Goodreads reading history to make inferences about who they are. Computes reading stats, generates AI-powered personality analyses, and serves results at shareable URLs.

## How It Works

Shelf Aware is a Claude Code skill that orchestrates a multi-step pipeline. There's no web form — you trigger everything from your terminal, and the results end up on a hosted web page you can share.

```
/shelf-aware https://goodreads.com/user/show/12345
```

Here's what happens when you run that:

### 1. Data Fetching

A Python script hits the Goodreads RSS feed for that user's "read" shelf. It paginates through all their books and pulls title, author, rating, date read, publication year, and cover image. Then it enriches each book with genre and page count data from the OpenLibrary API.

The user's profile must be public. Private profiles get a friendly error.

### 2. Stats Computation

A second Python script crunches 8 statistical analyses from the book data:

| Stat | What It Measures |
|---|---|
| **Hater vs Hype Index** | Do you rate above or below the crowd? Labels you a Contrarian Critic, Fair Judge, or Hype Beast. |
| **Reading Eras** | Books grouped by publication decade. Are you reading living authors or dead Victorians? |
| **Attention Span** | Page count distribution. Sprint Reader, Marathoner, or Ultramarathoner. |
| **Genre Radar** | Spider chart of your top genres with a diversity score. |
| **Reading Pace** | Books per month/year over time, with peak periods identified. |
| **Author Loyalty** | How often you return to the same authors. |
| **Rating Distribution** | Your 1-5 star histogram, average, and what % you give 5 stars. |
| **Reading Heatmap** | GitHub-style calendar of your reading activity over the past year. |

All stats include chart-ready data that renders client-side via Chart.js.

### 3. AI Analysis (8 Parallel Agents)

Claude Code launches 8 independent agents simultaneously, each analyzing the book list from a different angle. Each agent runs in its own isolated context — they can't see each other's work or pollute each other's outputs. Opus handles the analyses that require deeper pattern recognition; Sonnet handles the more structured ones.

Every agent receives the full book list as CSV and returns structured JSON. Agent 8 also reads the reader's own review text for deeper profiling.

#### Psychological Profile (Opus)

> You are analyzing a reader's bookshelf to build a psychological profile. Here are their books: `<books_json>`. Return JSON with these fields: `{"archetype": "one word or short phrase", "values": ["3-5 core values"], "traits": ["3-5 personality traits"], "searching_for": "what this person is searching for in life based on reading patterns", "summary": "2-3 sentence psychological summary"}`

#### Roast My Shelf (Sonnet)

> You are a witty literary critic roasting someone's bookshelf. Here are their books: `<books_json>`. Be funny but not mean-spirited. Return JSON: `{"roast": "2-3 paragraph roast of their reading taste", "guilty_pleasures": ["2-3 books/patterns that are guilty pleasures"], "stereotype": "the reader stereotype they fit", "one_liner": "a snarky one-liner summary of their entire shelf"}`

#### Vibe Check (Sonnet)

> You are a cultural aesthetics analyst doing a vibe check on someone's bookshelf. Here are their books: `<books_json>`. Return JSON: `{"primary_aesthetic": "their primary aesthetic", "secondary_aesthetic": "secondary aesthetic", "playlist_vibe": "describe the playlist that matches their reading taste", "bookshelf_as_place": "if their bookshelf were a place, describe it", "summary": "1-2 sentence overall vibe summary"}`

#### Red/Green Flags (Sonnet)

> You are analyzing a reader's bookshelf for dating red and green flags. Here are their books: `<books_json>`. Use specific book titles as evidence. Return JSON: `{"green_flags": [{"flag": "the green flag", "evidence": "specific books/patterns as evidence"}]` (exactly 3), `"red_flags": [{"flag": "the red flag", "evidence": "specific books/patterns as evidence"}]` (exactly 3)`}`

#### Blind Spots (Sonnet)

> You are a literary advisor identifying gaps in someone's reading. Here are their books: `<books_json>`. Return JSON: `{"gaps": [{"area": "gap area name", "description": "why this is a blind spot", "recommendations": ["2-3 specific book recommendations"]}]` (3-5 gaps)`}`

#### Reading Evolution (Opus)

> You are a literary historian analyzing the evolution of someone's reading taste over time. Here are their books: `<books_json>`. Look at dates_read and publication years to identify distinct phases. Return JSON: `{"eras": [{"name": "era name", "period": "approximate time period", "description": "what characterized this reading era"}], "trajectory": "overall trajectory description", "prediction": "prediction for what they'll read next and why"}`

#### Book Recommendations (Opus)

> You are an expert book recommender. Analyze this reader's complete bookshelf to understand their taste deeply — genres they love, authors they return to, themes that resonate, ratings patterns, and how their taste has evolved. Here are their books: `<books_json>`. Recommend books they have NOT already read. Be specific and thoughtful — no obvious picks they've surely already heard of. Return JSON: `{"top_10": [{"title": "book title", "author": "author name", "reason": "1-2 sentence personalized reason why this reader specifically would love this book"}], "deep_cuts": [{"title": "book title", "author": "author name", "reason": "why this lesser-known book matches their taste"}]` (3-5 obscure/underrated picks), `"next_favorite_author": {"name": "author name", "why": "why this author is perfect for them", "start_with": "specific book to start with"}, "wildcard": {"title": "book title", "author": "author name", "reason": "a surprising pick outside their comfort zone that they'd still love, and why"}}`

#### Between the Lines — Deep Profile (Opus)

> You are a literary detective conducting a deep biographical and psychological profile of a person based solely on their reading history and reviews. Read the book list from `books.csv` and their reviews from `reviews.txt` — the reader's own words about books they've read. Working from titles, authors, ratings, dates read, publication years, reading patterns, AND review text — construct a detailed profile. Think like a detective: what do their choices AND their words reveal about their age, gender, education, career, beliefs, personality, and inner life? For each section, separate observations into **Strong Inferences** (confident claims backed by clear patterns, citing specific titles and quoting reviews) and **Speculative** (plausible guesses from weaker signals). Sections: The Basics, Education & Intellectual Life, Career & Life Stage, Reading Tastes: What They Love, Reading Tastes: What They Avoid, Intellectual & Ideological Profile, Personality & Inner Life. End with a `summary_portrait`. Return JSON: `{"sections": [{"title": "...", "strong_inferences": ["..."], "speculative": ["..."]}], "summary_portrait": "2-4 sentence vivid portrait"}`

### 4. Storage & Serving

Everything gets combined and stored in a Postgres database on Render. A FastAPI server serves the results as pre-rendered HTML pages — no LLM calls happen on the server. The results page has a tabbed layout so you can flip between the overview charts and each AI analysis.

The shareable URL looks like: `shelf-aware.onrender.com/u/12345`

## Comparison Mode

You can compare two readers head-to-head:

```
/shelf-aware compare https://goodreads.com/user/show/12345 https://goodreads.com/user/show/67890
```

This runs the full individual pipeline for both people, then adds comparison-specific analysis on top.

### Hard Analytics (Python-computed)

- **The Shared Shelf** — How many books they've both read, visualized as a venn-style bar.
- **The Rift** — Books they both read with the biggest rating disagreements. Shows star ratings side by side. ("You both read *Dune*. Alex: 5 stars. Taylor: 1 star.")
- **Pace vs Patience** — Side-by-side books per year and average page count.
- **Genre Overlap** — Dual-layer radar chart showing where tastes align and diverge.
- **Decades Alignment** — Do they exist in the same era? Dual bar chart of publication decades.
- **Rating Personality Clash** — Hype Beast vs Contrarian Critic matchup.

### AI Insights (2 Parallel Opus Agents)

Both comparison agents receive both readers' full book lists and run simultaneously in isolated contexts.

#### Dynamics & Personality (Opus)

> You are a witty literary analyst comparing two readers. Reader A ("`<user_a>`") books: `<books_a_json>`. Reader B ("`<user_b>`") books: `<books_b_json>`. Their comparison stats: `<comparison_stats_json>`. Generate highly specific, entertaining analysis referencing actual book titles from their shelves. Return JSON:
> ```json
> {
>   "compatibility_score": "<0-100 integer>",
>   "compatibility_line": "a snarky one-liner about their compatibility",
>   "dynamic_trope": "assign them a classic dynamic (e.g. 'The Golden Retriever & The Black Cat')",
>   "dynamic_explanation": "2-3 sentences explaining the trope with evidence from their actual books",
>   "desert_island": "2-3 paragraph scenario of what happens if stranded on an island, based purely on knowledge from their books. Reference specific titles.",
>   "what_they_argue_about": "the fundamental philosophical difference between them based on reading tastes, with specific book evidence",
>   "whos_main_character": {
>     "main_character": "name of the person who reads like a protagonist",
>     "sidekick": "the other person",
>     "explanation": "why, referencing their genres and specific books"
>   }
> }
> ```

#### Comparison Recommendations (Opus)

> You are an expert book recommender analyzing two readers' shelves to find perfect crossover recommendations. Reader A ("`<user_a>`") books: `<books_a_json>`. Reader B ("`<user_b>`") books: `<books_b_json>`. Return JSON:
> ```json
> {
>   "bridge_books": [
>     {"title": "book title", "author": "author name", "why": "why this book perfectly intersects BOTH of their distinct tastes — reference specific books/genres from each person's shelf"}
>   ] // exactly 3 books that NEITHER person has read
>   "book_swap": {
>     "a_should_read": [
>       {"title": "a book from B's shelf", "author": "author", "why": "why <user_a> specifically would love this based on their taste"}
>     ] // exactly 3 — must be books Person B has actually read that Person A has not
>     "b_should_read": [
>       {"title": "a book from A's shelf", "author": "author", "why": "why <user_b> specifically would love this based on their taste"}
>     ] // exactly 3 — must be books Person A has actually read that Person B has not
>   }
> }
> ```

The comparison page is at: `shelf-aware.onrender.com/compare/12345-vs-67890`

## Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/) for running CLI scripts
- A Postgres database (Render provides one via the Blueprint)
- `DATABASE_URL` environment variable set

### Local Development

```bash
# Install CLI dependencies
cd shelf-aware
uv sync

# Initialize the database
DATABASE_URL=postgresql://... uv run cli/init_db.py

# Test the data fetcher
uv run cli/fetch_goodreads.py 12345

# Run the server locally
pip install -r requirements.txt
DATABASE_URL=postgresql://... uvicorn server.main:app --reload
```

### Deploy to Render

The included `render.yaml` Blueprint sets up a web service and Postgres database. Push to a connected repo and Render handles the rest.

After deploying, initialize the database:

```bash
DATABASE_URL=<render-postgres-url> uv run cli/init_db.py
```

### Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres connection string |

## Architecture

```
/shelf-aware <url>
    │
    ├─ cli/fetch_goodreads.py      Fetches RSS + enriches via OpenLibrary
    ├─ cli/compute_stats.py        Computes 8 statistical analyses
    ├─ 8 parallel Claude agents    AI personality analyses + deep profile + recommendations
    ├─ cli/store_results.py        Upserts everything into Postgres
    │
    └─ Result: shelf-aware.onrender.com/u/<id>

/shelf-aware compare <url1> <url2>
    │
    ├─ (full pipeline for both users)
    ├─ cli/compute_comparison.py   Hard comparison analytics
    ├─ 2 parallel Claude agents    Dynamics + cross-reader recommendations
    ├─ cli/store_results.py --comparison
    │
    └─ Result: shelf-aware.onrender.com/compare/<id1>-vs-<id2>
```

All AI work happens locally in Claude Code. The server only reads from Postgres and renders HTML — no API keys or LLM calls required on the server side.

## Project Structure

```
shelf-aware/
├── cli/
│   ├── fetch_goodreads.py       # RSS fetcher + OpenLibrary enrichment
│   ├── compute_stats.py         # 8 statistical computations
│   ├── compute_comparison.py    # Head-to-head comparison analytics
│   ├── store_results.py         # Upsert results into Postgres
│   └── init_db.py               # Create database tables
├── server/
│   ├── main.py                  # FastAPI app
│   ├── database.py              # asyncpg connection pool
│   ├── routers/
│   │   ├── profiles.py          # GET /u/<id>
│   │   └── comparisons.py       # GET /compare/<id1>-vs-<id2>
│   ├── templates/
│   │   ├── base.html            # Layout (Tailwind + Chart.js CDN)
│   │   ├── home.html            # Landing page + recent analyses
│   │   ├── profile.html         # Single-user results (tabbed)
│   │   └── compare.html         # Head-to-head comparison
│   └── static/
│       ├── css/style.css
│       └── js/charts.js         # Chart rendering functions
├── pyproject.toml               # CLI dependencies (uv)
├── requirements.txt             # Server dependencies
└── render.yaml                  # Render Blueprint
```
