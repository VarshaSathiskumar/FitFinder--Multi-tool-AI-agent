# FitFindr — Multi-Tool AI Agent

FitFindr is a secondhand styling assistant. You describe what you're looking for — a vintage graphic tee, a pair of wide-leg trousers, size and budget optional — and it finds matching thrift listings, suggests outfits using your existing wardrobe, and generates a shareable caption for your find.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

**Run the web interface:**
```bash
python app.py
```
Then open the localhost URL shown in your terminal (usually `http://localhost:7860`).

**Run the agent directly:**
```bash
python agent.py
```

**Run tests:**
```bash
pytest tests/
```

---

## Project Structure

```
├── agent.py              # Planning loop — run_agent()
├── app.py                # Gradio UI — handle_query()
├── tools.py              # The three tools
├── tests/
│   └── test_tools.py     # 20 pytest tests
├── utils/
│   └── data_loader.py    # load_listings(), get_example_wardrobe(), etc.
├── data/
│   ├── listings.json     # 40 mock secondhand listings
│   └── wardrobe_schema.json
└── planning.md           # Full spec and agent diagram
```

---

## Tool Inventory

### Tool 1 — `search_listings`

**Purpose:** Finds secondhand listings that match a user's description, size, and budget. This is the only tool that does no LLM call — it's pure local filtering and keyword scoring over `data/listings.json`.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the item — e.g. `"vintage graphic tee"`. Scored against each listing's title, description, category, style tags, colors, and brand. |
| `size` | `str \| None` | Size to filter by — e.g. `"M"`, `"S/M"`, `"W30"`. Case-insensitive substring match. `None` skips size filtering. |
| `max_price` | `float \| None` | Price ceiling in dollars (inclusive). `None` skips price filtering. |

**Output:** `list[dict]` — listing dicts sorted by relevance score descending. Each dict has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price` (float), `colors`, `brand`, `platform`. Returns `[]` if nothing matches — never raises.

---

### Tool 2 — `suggest_outfit`

**Purpose:** Given the thrifted item the user is considering and their existing wardrobe, asks the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfits. If the wardrobe is empty, it falls back to general styling advice using common wardrobe staples.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A single listing dict — the item the user is considering buying. Must have at least `title`, `category`, `style_tags`, `colors`. |
| `wardrobe` | `dict` | Wardrobe dict with an `"items"` key. Each item has `name`, `category`, `colors`, `style_tags`. The list may be empty. |

**Output:** `str` — a non-empty outfit suggestion. When the wardrobe has items, suggestions reference specific pieces by name (e.g. "pair with your baggy dark-wash jeans"). When the wardrobe is empty, suggestions describe item types (e.g. "try with high-waisted wide-leg trousers").

---

### Tool 3 — `create_fit_card`

**Purpose:** Turns the outfit suggestion into a 2–4 sentence OOTD-style caption — casual, first-person, suitable for Instagram or TikTok. Uses `temperature=1.2` so each run produces a distinct caption even for the same input. Mentions the item name, price, and platform once each.

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion from `suggest_outfit`. If empty or whitespace-only, the tool returns an error string without calling the LLM. |
| `new_item` | `dict` | The listing dict. Must have `title`, `price`, `platform` to compose the caption. |

**Output:** `str` — a casual caption, e.g. *"found this y2k baby tee on depop for $18 and it goes with everything in my closet. baggy jeans, chunky sneakers, done."* Returns a descriptive error string (not an exception) if `outfit` is empty.

---

## Planning Loop

`run_agent(query, wardrobe)` runs a strictly linear, sequential loop. Each step only executes if all prior steps produced usable output.

```
User query
    │
    ▼
Step 1 — _new_session(query, wardrobe)
    │
    ▼
Step 2 — Parse query with regex
    │   extract: description, size, max_price
    │   store in session["parsed"]
    │
    ▼
Step 3 — search_listings(description, size, max_price)
    │   store in session["search_results"]
    │
    ├── results == [] ──► session["error"] = "No listings found..."
    │                     return session immediately
    │
    ▼
Step 4 — session["selected_item"] = search_results[0]
    │
    ▼
Step 5 — suggest_outfit(selected_item, wardrobe)
    │   store in session["outfit_suggestion"]
    │
    ├── empty / exception ──► session["error"] = "Outfit suggestion failed."
    │                         return session immediately
    │
    ▼
Step 6 — create_fit_card(outfit_suggestion, selected_item)
    │   store in session["fit_card"]
    │   (soft error — returns error string, does not exit early)
    │
    ▼
Step 7 — return session
    (session["error"] is None on the happy path)
```

**Query parsing** uses regex rather than an LLM call:
- `max_price`: matches `under $N` or `$N or less`
- `size`: matches common size tokens (`XXS`, `XS`, `S`, `M`, `L`, `XL`, `XXL`, `W\d+`, `one size`)
- `description`: the query string with price and size fragments stripped

This keeps parsing fast, free, and deterministic — no API call needed for something a regex handles cleanly.

---

## State Management

All state lives in a single `session` dict created at the start of each `run_agent()` call. No global variables. Each step reads from earlier fields and writes to later ones — data flows strictly forward.

| Field | Type | Written by | Read by |
|-------|------|-----------|---------|
| `query` | `str` | `_new_session` | parse step |
| `parsed` | `dict` | parse step | `search_listings` call |
| `search_results` | `list[dict]` | `search_listings` result | `selected_item` assignment |
| `selected_item` | `dict` | `results[0]` | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `dict` | `_new_session` (passed in) | `suggest_outfit` |
| `outfit_suggestion` | `str` | `suggest_outfit` result | `create_fit_card` |
| `fit_card` | `str` | `create_fit_card` result | final output / UI |
| `error` | `str \| None` | any failure branch | caller checks this first |

No tool reads directly from the session dict. The planning loop extracts the right values from the session and passes them as named arguments. This means each tool is independently testable without any session object.

---

## Error Handling

### `search_listings` — empty results

**Failure mode:** the price ceiling, size filter, or keyword scoring eliminates all 40 listings.

**Agent response:** sets `session["error"]` with an actionable message and returns immediately. `suggest_outfit` and `create_fit_card` are never called.

**Concrete example from testing:**
```
query: "designer ballgown size XXS under $5"
→ search_listings returns []
→ session["error"] = "No listings found matching your search.
   Try broader keywords, a higher budget, or skip the size filter."
→ session["outfit_suggestion"] = None
→ session["fit_card"] = None
```

The message names all three constraints the user can relax — keywords, budget, size — rather than just saying "no results."

---

### `suggest_outfit` — LLM failure or empty response

**Failure mode:** the Groq API raises an exception, or the response string is empty or whitespace-only.

**Agent response:** catches the exception with a `try/except`, checks the return value, sets `session["error"] = "Outfit suggestion failed. Please try again."`, and returns immediately. `create_fit_card` is not called.

**Concrete example from testing:**
```python
# Mocked in test_suggest_outfit_empty_wardrobe_does_not_crash:
wardrobe = {"items": []}
# suggest_outfit takes the empty-wardrobe branch and still returns a string
# (no crash, no early exit)
→ result = "You just scored an adorable thrift find. Since this is your
            first item, let's build some outfits with common wardrobe
            staples..."
```

The empty wardrobe case was the most important edge to guard — an agent that crashes when a new user has no wardrobe items is unusable for exactly the people who need the most styling help.

---

### `create_fit_card` — empty outfit string

**Failure mode:** `outfit` parameter is empty or whitespace-only (shouldn't happen on the happy path, but guarded defensively).

**Agent response:** `create_fit_card` itself returns an error string without calling the LLM or raising. The agent stores the string in `session["fit_card"]` and still returns the session — the user still sees the outfit suggestion even if the caption failed.

**Concrete example from testing:**
```python
result = create_fit_card("", item)
# → "Error: no outfit suggestion available — run suggest_outfit first
#    before creating a fit card."
# No exception raised. Session is still returned with outfit_suggestion intact.
```

This is a "soft error" — the user loses the caption but keeps everything else. It's a better degradation than blocking the whole response.

---

## AI Usage

### Instance 1 — Implementing `suggest_outfit` and `create_fit_card`

**What I gave the AI:**
- The full Tool 2 and Tool 3 spec sections from `planning.md` (inputs with types, output format, the two prompt branches for empty vs. non-empty wardrobe, the `temperature` requirement)
- A sample listing dict and the wardrobe schema from `wardrobe_schema.json`
- The `_get_groq_client()` helper already in `tools.py`

**What it produced:**
Both tool implementations were structurally correct — correct branch logic for empty wardrobe, correct use of `_get_groq_client()`, correct return types. The initial temperature for `create_fit_card` was set to `0.9`.

**What I changed:**
After running `create_fit_card` three times on the same input and getting captions that were identically structured (same sentence rhythm, same opener), I raised the temperature to `1.2`. The spec said outputs should "sound different each time" — at `0.9` they were varying in word choice but not in structure. At `1.2` the captions were genuinely distinct in tone and opening. I also confirmed that `suggest_outfit` correctly passes wardrobe item names into the prompt by inspecting the actual prompt string in the tests (`assert "Cargo pants" in prompt_text`), not just checking the return value.

---

### Instance 2 — Implementing `run_agent()` planning loop

**What I gave the AI:**
- The full Planning Loop and State Management sections from `planning.md` (the numbered step-by-step logic, the branch conditions, the state table)
- The Architecture diagram from `planning.md` (the full ASCII flowchart showing Branch A, B, C, D)
- The `_new_session()` dict definition from `agent.py`

**What it produced:**
The generated loop followed the step structure correctly — initialized session, parsed with regex, branched on empty results, stored `selected_item`, called the three tools in order, returned the session. The `suggest_outfit` failure branch was present but only caught exceptions, not the empty-string case.

**What I changed:**
I added the `not outfit or not outfit.strip()` check after the `try/except` block, per the spec's Branch C definition: *"if `suggest_outfit` raises an exception or the returned string is empty/whitespace."* The generated code only handled the exception half. I also moved the `import re` inside the function body to keep the module-level imports clean (the generator put it at the top of the file, but since it's only used in `run_agent`, keeping it local is cleaner). Finally I verified state identity in testing — `assert session['selected_item'] is session['search_results'][0]` — to confirm the same dict object was flowing through, not a copy.
