# Shelf Aware — Setup & Usage Guide

## Prerequisites

You need three things before your first run:

1. **Claude Code** — The CLI tool. This is where you'll trigger analyses.
2. **uv** — Python package runner. Install it if you don't have it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. **A Postgres database** — For storing results and serving them on the web. Render gives you a free one.

## First-Time Setup

### Step 1: Install Python dependencies

```bash
cd /Users/genehong/claude_sandbox/shelf-aware
uv sync
```

This installs httpx, psycopg2-binary, and pydantic for the CLI scripts.

### Step 2: Set up the database

**Option A: Use Render (recommended for shareable URLs)**

1. Push the repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com) → New → Blueprint
3. Connect your repo — Render reads `render.yaml` and creates both the web service and a Postgres database
4. Once created, grab the **Internal Database URL** from the Render Postgres dashboard
5. Also grab the **External Database URL** — you'll need this for running CLI scripts locally

**Option B: Local Postgres (for testing)**

```bash
createdb shelf_aware
# Your DATABASE_URL will be something like:
# postgresql://localhost:5432/shelf_aware
```

### Step 3: Initialize the database tables

```bash
DATABASE_URL="postgresql://..." uv run cli/init_db.py
```

You should see: `Tables created successfully.`

### Step 4: Set your DATABASE_URL

So you don't have to pass it every time, add it to a `.env` file in the project root:

```bash
cd /Users/genehong/claude_sandbox/shelf-aware
cp .env.example .env
# Edit .env and paste your DATABASE_URL
```

Or export it in your shell profile:

```bash
export DATABASE_URL="postgresql://..."
```

### Step 5: Deploy the web server (if using Render)

If you used the Render Blueprint in Step 2, the server is already deployed. It serves results at `shelf-aware.onrender.com` (or whatever your Render app name is).

To run the server locally instead:

```bash
pip install -r requirements.txt
DATABASE_URL="postgresql://..." uvicorn server.main:app --reload
```

The server runs at `http://localhost:8000`.

## Usage

### Analyze a single profile

Open Claude Code and run:

```
/shelf-aware https://goodreads.com/user/show/12345
```

You can also use just the numeric ID:

```
/shelf-aware 12345
```

Or various URL formats — the script extracts the ID from whatever you give it:

```
/shelf-aware https://www.goodreads.com/user/show/12345-some-username
/shelf-aware https://goodreads.com/review/list/12345?shelf=read
```

**What happens next:**

1. Claude Code fetches the user's reading history from Goodreads RSS (~1-2 min for large libraries, the script paginates with polite delays)
2. Each book gets enriched with genre/page data from OpenLibrary (~30s-2min depending on library size)
3. Stats are computed locally (instant)
4. 7 AI agents run in parallel analyzing the book list (~30-60s)
5. Everything gets stored in Postgres
6. You get a shareable URL printed in your terminal

**The profile must be public.** If the user's Goodreads profile is private, the RSS feed won't return any data and you'll get an error. The person needs to go to Goodreads → Settings → Privacy and make sure their profile isn't set to "private."

### Compare two profiles

```
/shelf-aware compare https://goodreads.com/user/show/12345 https://goodreads.com/user/show/67890
```

This runs the full individual analysis for both people (so each gets their own profile page), then runs additional comparison-specific analysis:

- Python computes hard stats: shared books, rating disagreements, genre overlap, pace comparison, etc.
- 2 more AI agents run in parallel: one for dynamics/personality (compatibility score, desert island scenario, etc.), one for cross-reader book recommendations (bridge books + book swap)

You get three URLs:
- Individual profile for person A
- Individual profile for person B
- The comparison page

### View results

**On the web:**
- Single profile: `shelf-aware.onrender.com/u/12345`
- Comparison: `shelf-aware.onrender.com/compare/12345-vs-67890`
- Home page with recent analyses: `shelf-aware.onrender.com`

**Via API (raw JSON):**
- `shelf-aware.onrender.com/api/profile/12345`

### Re-run a profile

If you run `/shelf-aware` on the same user again, it upserts — the existing row gets updated with fresh data and analysis. Useful if someone has read more books since the last run.

## What You Get

### Single Profile Page

A tabbed interface with:

- **Overview** — 8 charts (rating distribution, genre radar, reading eras, attention span, reading pace, author loyalty, hater/hype scatter, reading heatmap) plus key metric cards
- **Psych Profile** — Archetype, core values, personality traits, what they're searching for
- **Roast** — Roast of their taste, guilty pleasures, reader stereotype, snarky one-liner
- **Vibe Check** — Primary/secondary aesthetic, playlist vibe, bookshelf-as-a-place
- **Flags** — 3 green flags and 3 red flags for dating, with specific book evidence
- **Blind Spots** — Gaps in their reading with book recommendations to fill them
- **Evolution** — Reading eras over time, trajectory, prediction for what's next
- **Recs** — Top 10 personalized picks, deep cuts, next favorite author, wildcard

### Comparison Page

- Compatibility score with snarky one-liner
- Dynamic trope ("The Golden Retriever & The Black Cat")
- Side-by-side stat cards
- Shared shelf venn bar
- The Rift (biggest rating disagreements on shared books, star-by-star)
- Pace vs Patience matchup
- Rating personality clash
- Dual genre radar chart
- Dual decades bar chart
- Who's the main character
- Desert island scenario
- What they argue about
- 3 bridge books (neither has read, intersects both tastes)
- Book swap (3 recs from each person's shelf for the other)

## Troubleshooting

**"Goodreads profile appears to be private or invalid"**
The user's Goodreads account is set to private. They need to make it public in their Goodreads settings, or at minimum make their "read" shelf visible.

**"No books found on the read shelf"**
The user exists but has no books on their "read" shelf. They might use a different shelf name, or they just haven't marked any books as read.

**"DATABASE_URL not set"**
The `DATABASE_URL` environment variable isn't available. Either export it in your shell, or add it to the `.env` file in the project root.

**OpenLibrary enrichment is slow**
The script hits the OpenLibrary API once per book with a 0.5s delay between requests. For someone with 500 books, that's ~4 minutes of enrichment. The analysis will still work without it — genres will just be less accurate (defaulting to "Other").

**Server returns 404 for a profile**
The profile hasn't been analyzed yet. Run `/shelf-aware <url>` first to generate and store the results.
