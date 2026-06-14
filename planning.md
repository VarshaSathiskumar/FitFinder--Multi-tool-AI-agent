# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads the full listings dataset from `data/listings.json` (via `load_listings()`), filters it by price ceiling and size, scores each surviving listing by keyword overlap against the user's description, and returns a ranked list of matching listing dicts. This is purely local — no LLM call.

**Input parameters:**
- `description` (str): Keywords the user used to describe what they want, e.g. `"vintage graphic tee"`. Used for keyword-overlap scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): Size string to filter by, e.g. `"M"` or `"S/M"`. If provided, only listings whose `size` field contains this string (case-insensitive) are kept. If `None`, no size filtering is applied.
- `max_price` (float | None): Maximum price in dollars (inclusive). Only listings with `price <= max_price` are kept. If `None`, no price filtering is applied.

**What it returns:**
A `list[dict]` sorted by relevance score descending. Each dict is one listing from `listings.json` with these exact fields:
- `id` (str): unique identifier, e.g. `"lst_002"`
- `title` (str): listing name, e.g. `"Y2K Baby Tee — Butterfly Print"`
- `description` (str): seller's item description
- `category` (str): one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[str]): aesthetic tags, e.g. `["vintage", "graphic tee", "y2k"]`
- `condition` (str): one of `excellent`, `good`, `fair`
- `price` (float): listed price in dollars, e.g. `18.0`
- `colors` (list[str]): e.g. `["white", "pink"]`
- `brand` (str | None): brand name or `null`
- `platform` (str): one of `depop`, `thredUp`, `poshmark`

Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
If the returned list is empty, the agent sets `session["error"] = "No listings found matching your search. Try broader keywords, a higher budget, or skip the size filter."` and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM with a prompt that either combines the new thrifted item with named pieces from the user's existing wardrobe (if the wardrobe has items) or asks for general styling advice (if the wardrobe is empty). Returns a string with 1–2 complete outfit suggestions.

**Input parameters:**
- `new_item` (dict): A single listing dict (same shape as one element of what `search_listings` returns — must have at least `title`, `category`, `style_tags`, `colors`).
- `wardrobe` (dict): A wardrobe dict with an `"items"` key whose value is a list of wardrobe item dicts. Each wardrobe item has: `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), `notes` (str | None). The list may be empty.

**What it returns:**
A non-empty string with 1–2 outfit suggestions. If the wardrobe has items, the suggestions reference specific named wardrobe pieces (e.g. "pair it with your baggy straight-leg jeans and white ribbed tank"). If the wardrobe is empty, the suggestions describe general item types that would work well (e.g. "pair with high-waisted wide-leg trousers and chunky sneakers"). Never returns an empty string.

**What happens if it fails or returns nothing:**
If the LLM call raises an exception or returns an empty/whitespace string, the agent sets `session["error"] = "Outfit suggestion failed. Please try again."` and returns the session without calling `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM at a higher temperature (`~0.9`) to generate a 2–4 sentence OOTD-style caption suitable for Instagram or TikTok. The caption names the thrifted item, its price, and the platform it was found on, and captures the outfit vibe in specific, casual language.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. If this is empty or whitespace-only, the tool skips the LLM call and returns an error string.
- `new_item` (dict): The listing dict for the thrifted item. Must have at least `title` (str), `price` (float), and `platform` (str) to compose the caption.

**What it returns:**
A 2–4 sentence string written in casual first-person, e.g.: *"thrifted this Nirvana tee off Depop for $22 and honestly it's my new favourite thing. baggy jeans, chunky sneakers — done. if vintage is your thing you already know."* Returns a descriptive error string (not an exception) if `outfit` is empty.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace, `create_fit_card` immediately returns the string `"Could not generate a fit card: outfit suggestion was empty."` — the agent stores this in `session["fit_card"]` and still returns the session (this is a graceful degradation, not a hard stop, because the user already has the outfit suggestion).

---

### Additional Tools (if any)

None for the base implementation.

---

## Planning Loop

The agent runs a strictly linear, sequential loop with early-exit branches on failure. Here is the exact conditional logic:

1. **Initialize** — call `_new_session(query, wardrobe)` to create the session dict.

2. **Parse query** — extract `description`, `size`, and `max_price` from the raw query string using regex:
   - `max_price`: match `under \$?(\d+(\.\d+)?)` or `\$?(\d+(\.\d+)?)\s+or\s+less`; if no match, set `None`.
   - `size`: match common size tokens (`\b(XXS|XS|S|M|L|XL|XXL|W\d+|one size)\b`) case-insensitively; if no match, set `None`.
   - `description`: strip the size and price fragments from the query; use the remainder as the description string.
   - Store all three in `session["parsed"]`.

3. **Call `search_listings`** — pass `session["parsed"]["description"]`, `session["parsed"]["size"]`, `session["parsed"]["max_price"]`.
   - Store the return value in `session["search_results"]`.
   - **Branch A (empty results):** if `len(session["search_results"]) == 0`, set `session["error"] = "No listings found matching your search. Try broader keywords, a higher budget, or skip the size filter."` and `return session`. Stop here.
   - **Branch B (results found):** set `session["selected_item"] = session["search_results"][0]` and continue.

4. **Call `suggest_outfit`** — pass `session["selected_item"]` and `session["wardrobe"]`.
   - Store the return value in `session["outfit_suggestion"]`.
   - **Branch C (failure):** if `suggest_outfit` raises an exception or the returned string is empty/whitespace, set `session["error"] = "Outfit suggestion failed. Please try again."` and `return session`. Stop here.
   - **Branch D (success):** continue.

5. **Call `create_fit_card`** — pass `session["outfit_suggestion"]` and `session["selected_item"]`.
   - Store the return value in `session["fit_card"]`.
   - No early exit here — `create_fit_card` handles its own failure by returning an error string rather than raising.

6. **Return session** — all fields populated; `session["error"]` is `None` on the happy path.

The agent never calls a later tool if an earlier tool produced no usable output.

---

## State Management

All state lives in a single `session` dict created at the start of each `run_agent` call. No global variables. Fields and what populates them:

| Field | Type | Set by | Used by |
|-------|------|--------|---------|
| `query` | str | `_new_session` | parse step |
| `parsed` | dict (`description`, `size`, `max_price`) | parse step | `search_listings` |
| `search_results` | list[dict] | `search_listings` result | selected_item assignment |
| `selected_item` | dict | `results[0]` after search | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | `_new_session` (passed in) | `suggest_outfit` |
| `outfit_suggestion` | str | `suggest_outfit` result | `create_fit_card` |
| `fit_card` | str | `create_fit_card` result | final output |
| `error` | str \| None | set on any failure | caller checks this first |

Data flows strictly forward — each step reads from earlier fields and writes to later ones. No tool reads from the session directly; the planning loop extracts the right values and passes them as arguments.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | Returns `[]` — no listings pass the price/size/keyword filters | Set `session["error"]` to a user-friendly message suggesting they broaden their search; return session immediately without calling further tools |
| `suggest_outfit` | LLM call raises an exception, or LLM returns an empty/whitespace string | Set `session["error"]` to `"Outfit suggestion failed. Please try again."`; return session immediately without calling `create_fit_card` |
| `create_fit_card` | `outfit` parameter is empty or whitespace-only | Return a descriptive error *string* (not raise); agent stores it in `session["fit_card"]` and still returns the session — the user still gets the outfit suggestion |

---

## Architecture

```
User query: "vintage graphic tee under $30, size M"
    │
    ▼
Planning Loop — run_agent() ─────────────────────────────────────────────┐
    │  _new_session(query, wardrobe)                                      │
    │  parse query → description="vintage graphic tee", size="M",        │
    │                max_price=30.0                                       │
    │                                                                     │
    ├─► search_listings(description, size, max_price)                     │
    │       │  filter listings by price ≤ 30.0 and size contains "M"     │
    │       │  score each by keyword overlap; drop score=0               │
    │       │  return list[dict] sorted by score desc                    │
    │       │                                                             │
    │       ├── results == [] ──► [ERROR] session["error"] = "No         │
    │       │                     listings found..." → return session ───►┘
    │       │
    │       │  results = [{"id":"lst_002","title":"Y2K Baby Tee",
    │       │               "price":18.0,"platform":"depop",...}, ...]
    │       ▼
    │   session["search_results"] = results
    │   session["selected_item"]  = results[0]
    │
    ├─► suggest_outfit(new_item=selected_item, wardrobe=session["wardrobe"])
    │       │  if wardrobe["items"] == [] → prompt LLM for general advice
    │       │  else → prompt LLM with named wardrobe pieces for specific
    │       │          outfit combinations; LLM call (Groq)
    │       │  return outfit suggestion string
    │       │
    │       ├── empty / exception ──► [ERROR] session["error"] =         │
    │       │                         "Outfit suggestion failed." → ─────►┘
    │       │
    │       │  outfit = "Pair with your baggy dark-wash jeans and white
    │       │            ribbed tank for a 90s look; or tuck into khaki
    │       │            trousers with a crossbody for a cleaner vibe."
    │       ▼
    │   session["outfit_suggestion"] = outfit
    │
    └─► create_fit_card(outfit=outfit_suggestion, new_item=selected_item)
            │  guard: if outfit is empty → return error string (no raise)
            │  else → prompt LLM (temp=0.9) for 2–4 sentence OOTD caption
            │          mentioning item name, price, platform
            │
            ├── outfit was empty ──► [SOFT ERROR] fit_card = error string
            │                        (session still returned; user keeps
            │                         the outfit suggestion they already have)
            │
            │  caption = "found this y2k baby tee on depop for $18 and
            │              it goes with everything. baggy jeans + chunky
            │              sneakers and it's giving 90s without trying."
            ▼
        session["fit_card"] = caption
        session["error"]    = None
            │
            ▼
        return session → listing + outfit suggestion + fit card caption
```

**Error path key:**
- `[ERROR]` (hard exit) — `session["error"]` is set; agent returns immediately; no further tools are called.
- `[SOFT ERROR]` — `create_fit_card` returns an error string instead of raising; the agent stores it in `session["fit_card"]` and still returns the session so the user sees the outfit suggestion.

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **`search_listings`**: Give Claude the Tool 1 spec above (inputs, return shape, scoring logic, failure case) plus the `load_listings()` docstring. Ask it to implement the function using Python's `str.lower()` for case-insensitive matching and a simple word-overlap counter for scoring. Verify by running three manual queries: one that should return results, one that returns nothing (price too low), and one filtered by size.

- **`suggest_outfit`**: Give Claude the Tool 2 spec, the wardrobe schema from `wardrobe_schema.json`, and a sample listing dict. Ask it to implement two prompt branches (empty vs. populated wardrobe) and call `_get_groq_client()`. Verify by running it against `get_example_wardrobe()` and `get_empty_wardrobe()` and checking that both return non-empty strings.

- **`create_fit_card`**: Give Claude the Tool 3 spec and a sample outfit suggestion string + listing dict. Ask it to set `temperature=0.9` in the Groq call and guard against an empty `outfit` string before calling the LLM. Verify that calling it with an empty string returns an error message string (not a crash) and that calling it with valid input returns something that reads like a real OOTD caption.

**Milestone 4 — Planning loop and state management:**

Give Claude the Planning Loop and State Management sections above, plus the `_new_session` dict definition from `agent.py`. Ask it to implement `run_agent()` following the exact step-by-step branch logic. Verify by running the two CLI test cases at the bottom of `agent.py`: the happy-path query should populate `fit_card` with a non-empty string and `error = None`; the no-results query should populate `error` with a non-empty string and leave `fit_card = None`.

---

## A Complete Interaction (Step by Step)

FitFindr is a styling assistant that helps users find thrifted clothing and see how it would fit into their wardrobe. Given a natural-language query, the agent parses out item keywords, size, and budget, then chains three tools in sequence: `search_listings` is triggered first to find candidate items, `suggest_outfit` is triggered once a top result is selected to generate pairing ideas using the user's existing wardrobe (or general styling advice if the wardrobe is empty), and `create_fit_card` is triggered last to turn the outfit suggestion into a shareable caption. If any tool returns empty or invalid output — no listings found, wardrobe missing, or outfit string blank — the agent sets `session["error"]` with a human-readable message and returns early rather than passing bad data to the next tool.

---

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The parse step extracts `description = "vintage graphic tee"`, `size = None` (no size token found), `max_price = 30.0` (matched `"under $30"`). These are stored in `session["parsed"]`. The agent calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. The tool loads all listings, keeps only those with `price <= 30.0`, then scores each by counting how many words from `"vintage graphic tee"` appear in each listing's `title + description + style_tags`. Listings with a score of 0 are dropped. Results are sorted by score descending and returned — for example, `lst_002` ("Y2K Baby Tee — Butterfly Print", $18, style_tags `["y2k", "vintage", "graphic tee"]`) scores 3 and comes back first.

**Step 2:**
`len(session["search_results"]) > 0`, so the agent does not exit early. It sets `session["selected_item"] = session["search_results"][0]` — the Y2K Baby Tee dict. It then calls `suggest_outfit(new_item=<baby_tee_dict>, wardrobe=<example_wardrobe>)`. Because `wardrobe["items"]` is non-empty (10 items), the tool builds a prompt listing each wardrobe item by name and style tags and asks the LLM to suggest 1–2 specific outfits using the new tee alongside named pieces. The LLM returns: "Try it with your baggy straight-leg dark-wash jeans and white ribbed tank underneath for a layered 90s look — finish with chunky sneakers. Or tuck it into your wide-leg khaki trousers with a simple crossbody for a more put-together vibe."

**Step 3:**
`session["outfit_suggestion"]` is non-empty, so the agent continues. It calls `create_fit_card(outfit=<suggestion_string>, new_item=<baby_tee_dict>)`. The tool checks that `outfit` is non-empty (it is), then prompts the LLM at temperature 0.9 to write a casual 2–4 sentence caption mentioning "Y2K Baby Tee", "$18", and "Depop". The LLM returns a caption, which is stored in `session["fit_card"]`. `session["error"]` remains `None`.

**Final output to user:**
The user sees three things: (1) the matched listing — "Y2K Baby Tee — Butterfly Print, $18 on Depop, condition: excellent"; (2) the outfit suggestion — the two specific combinations referencing their own wardrobe pieces; (3) the fit card caption — e.g. *"found this y2k baby tee on depop for $18 and it goes with literally everything in my closet. baggy jeans and chunky sneakers and it's giving 90s without trying too hard. thrift wins only."*
