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
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): ...
- `size` (str): ...
- `max_price` (float): ...

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
- `wardrobe` (dict): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

FitFindr is a styling assistant that helps users find thrifted clothing and see how it would fit into their wardrobe. Given a natural-language query, the agent parses out item keywords, size, and budget, then chains three tools in sequence: `search_listings` is triggered first to find candidate items, `suggest_outfit` is triggered once a top result is selected to generate pairing ideas using the user's existing wardrobe (or general styling advice if the wardrobe is empty), and `create_fit_card` is triggered last to turn the outfit suggestion into a shareable caption. If any tool returns empty or invalid output — no listings found, wardrobe missing, or outfit string blank — the agent sets `session["error"]` with a human-readable message and returns early rather than passing bad data to the next tool.

---

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent parses the query and extracts `description = "vintage graphic tee"`, `size = None` (none specified), and `max_price = 30.0`. It calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. The tool loads all listings, filters to items priced ≤ $30, scores each by keyword overlap with "vintage graphic tee", drops zero-score items, and returns a ranked list — for example, a Nirvana band tee listed at $22 on Depop.

**Step 2:**
The agent takes the top result (the Nirvana tee dict) and stores it as `session["selected_item"]`. It then calls `suggest_outfit(new_item=<nirvana_tee_dict>, wardrobe=<user_wardrobe>)`. Because the wardrobe contains items (baggy jeans, chunky sneakers), the tool builds a prompt listing those pieces and asks the LLM to suggest 1–2 specific outfit combinations using the new tee alongside named wardrobe items. The LLM returns something like: "Pair it with your wide-leg jeans and New Balance 550s for a 90s campus look; or tuck it into high-waisted cargo pants with platform boots for an edgier vibe."

**Step 3:**
With the outfit suggestion string in hand, the agent calls `create_fit_card(outfit=<suggestion_string>, new_item=<nirvana_tee_dict>)`. The tool prompts the LLM at a higher temperature to write a 2–4 sentence OOTD caption that mentions the item name, price ($22), and platform (Depop) naturally and captures the outfit vibe. If the outfit string were empty, the tool would return a descriptive error string instead of raising an exception.

**Final output to user:**
The user sees the fit card caption — e.g., *"thrifted this Nirvana tee off Depop for $22 and honestly can't stop wearing it 🖤 baggy jeans + chunky sneakers and it's giving full 90s without trying. if you know, you know."* — along with the outfit suggestion text and the matched listing details (title, price, platform, condition).
