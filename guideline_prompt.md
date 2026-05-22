You are an expert Senior Full-Stack Engineer and Multimodal ML Engineer.
You are extending an existing project called:
"Brainrot to English: Agent-Driven Diachronic Linguistic Analysis."

The FastAPI backend, LoRA fine-tuned translation model, orchestration 
agent, and Chrome Extension with floating computer pet UI are already 
specced or built. You are now upgrading the system to handle MULTIMODAL 
brainrot detection — specifically GIFs and images — because in internet 
vernacular, visual media functions as vocabulary, not decoration.

Sending a "skill issue" GIF is semantically equivalent to typing 
"skill issue." The system must treat them with equal linguistic weight.

---

### SCOPE CLARIFICATION — What Counts as a Brainrot Image/GIF

NOT brainrot visuals (ignore these entirely):
- Generic reaction GIFs (laughing, clapping, crying)
- Emojis rendered as images
- Profile pictures, product images, news photos
- Decorative page assets

IS brainrot visuals:
- Meme formats with established brainrot semantics:
  * Skibidi Toilet screenshots/GIFs
  * NPC TikTok-style walking loops
  * Sigma male grindset edits
  * "Skill issue" / "Ratio" / "L + ratio" reaction GIFs
  * Ohio meme imagery
  * Grimace Shake GIFs
  * Drake pointing meme (approval/disapproval format)
  * Distracted Boyfriend used as internet judgment meme
  * Any meme where meaning is ENTIRELY carried by cultural 
    context, not literal image content

The distinction: a laughing cat GIF conveys emotion (not brainrot). 
A "caught in 4k" GIF conveys a specific culturally-loaded verdict 
(brainrot). The test is whether a standard English speaker unfamiliar 
with internet culture would understand the communicated meaning from 
the image alone. If no → it is brainrot.

---

### Vision Model Required

Your existing text orchestration agent (OpenRouter) must be extended 
with a SEPARATE vision analysis call. Use:

  Model:   google/gemini-flash-1.5  (via OpenRouter)
  Reason:  Native GIF support without manual frame extraction,
           lowest cost-per-token with vision, already accessible 
           via your existing OpenRouter API key.

If Gemini Flash is unavailable, fall back to:
  Primary fallback:   openai/gpt-4o  (send first frame of GIF)
  Secondary fallback: anthropic/claude-3-5-sonnet (send first frame)

For fallbacks, GIF frame extraction must be handled client-side 
in the extension using the Canvas API before sending to the backend.

---

### Architecture Changes Required

#### New Data Flow for Image/GIF Detection

  User hovers over image/GIF on any webpage
            │
            ▼
  content_script.js detects hover on <img> or 
  elements with .gif src or animated class
            │
            ▼
  Quick pre-filter: is this likely a meme?
  (check: image dimensions near square or 16:9, 
   src contains known meme CDN domains like 
   tenor.com, giphy.com, i.imgur.com, or 
   filename heuristics like "meme", "ratio", 
   "sigma", "skill", "ohio" in the URL)
            │
    Yes ────┤
            ▼
  Extract image: fetch as base64 blob
  (for GIFs: send raw if Gemini, 
   extract frame 0 via Canvas if fallback model)
            │
            ▼
  POST /api/v1/analyze-image
  { "image_base64": "...", 
    "media_type": "image/gif | image/jpeg | image/png",
    "source_url": "..." }
            │
            ▼
  Backend calls vision agent → returns:
  { "is_brainrot": bool,
    "brainrot_meaning": "string or null",
    "equivalent_text": "string or null",
    "confidence_score": float,
    "formal_explanation": "string or null" }
            │
            ▼
  Pet bubble appears over the image with result

---

### New Backend Endpoint Required

#### POST /api/v1/analyze-image

Add to main.py:

Request schema (Pydantic):
  class ImageAnalysisRequest(BaseModel):
      image_base64: str          # base64 encoded image bytes
      media_type: str            # "image/gif", "image/jpeg", "image/png"
      source_url: Optional[str]  # original src URL, used as hint
      
Response schema:
  class ImageAnalysisResponse(BaseModel):
      is_brainrot: bool
      brainrot_meaning: Optional[str]   # e.g. "skill issue"
      equivalent_text: Optional[str]    # e.g. "This is your fault, 
                                        #        not worth addressing"
      formal_explanation: Optional[str] # full formal English meaning
      confidence_score: float
      flagged_for_review: bool          # true if confidence < 0.7

Pipeline inside the endpoint:
  1. Decode and validate base64 payload (reject if > 5MB, 422 error)
  2. Call agent.analyze_image_for_brainrot()
  3. If confidence < 0.7: trigger active learning flag 
     (same PostgreSQL staging logic as text pipeline)
  4. Return ImageAnalysisResponse

---

### New Agent Method Required

#### In agent.py — add method:

async def analyze_image_for_brainrot(
    self,
    image_base64: str,
    media_type: str,
    source_url: Optional[str] = None
) -> ImageAnalysisResponse:
    """
    Sends image/GIF to the vision-capable model via OpenRouter.
    
    System prompt must instruct the model to:
    - Determine if this image functions as brainrot vocabulary 
      in internet culture (NOT just any meme or reaction image)
    - If yes: identify what it communicates as a plain English 
      statement (the "equivalent_text")
    - If yes: provide a formal English explanation of the cultural 
      context (the "formal_explanation")
    - If no: return is_brainrot: false with null fields
    - Return structured JSON only — no prose, no markdown
    - Assign confidence_score based on certainty of classification
    
    The model call must use structured output / JSON mode.
    Use the Pydantic schema as the response format definition.
    
    Timeout: 12 seconds (vision calls are slower than text).
    On timeout: return is_brainrot: false, confidence: 0.0, 
    flagged_for_review: true — do NOT raise an exception.
    """

---

### Chrome Extension Changes Required

#### content_script.js — add image hover detection

In addition to the existing mouseup text selection listener, add:

1. A mouseover listener scoped to img elements and elements 
   whose computed background-image contains a URL ending in .gif

2. Debounce the hover trigger: only fire if the user hovers 
   for more than 600ms (prevents flooding on scroll)

3. Pre-filter function isMemeCandidate(imgElement):
   - Check src/currentSrc URL against known GIF CDN hostnames:
     tenor.com, giphy.com, media.giphy.com, i.imgur.com, 
     i.redd.it, cdn.discordapp.com
   - Check if image dimensions are roughly square (ratio 0.8–1.2) 
     or standard meme aspect ratio (1.77 for 16:9)
   - Check if URL contains any substring from a heuristic list:
     ["meme", "ratio", "sigma", "skill", "ohio", "npc", "cope",
      "skibidi", "grimace", "caught", "based", "slay", "rizz"]
   - Return true if ANY condition matches
   - This pre-filter avoids sending product photos and banners 
     to the API unnecessarily

4. If isMemeCandidate returns true:
   a. Show pet bubble in LOADING state near the image 
      (position above/below the image element, not at cursor)
   b. Fetch the image as a blob via fetch(imgSrc)
   c. Convert to base64
   d. For GIFs being sent to fallback models (non-Gemini):
      - Draw frame 0 to an off-screen Canvas element
      - Export canvas as image/jpeg base64
      - Note in the request that this is a GIF first-frame
   e. POST to /api/v1/analyze-image
   f. Update pet bubble with result

5. If is_brainrot is false in the response: hide bubble silently

6. Image hover detection must NOT interfere with the existing 
   text selection detection — they are independent listeners

---

#### pet_bubble.js — image result display mode

When displaying an image analysis result (as opposed to text), 
the pet bubble speech panel must show:

  ┌─────────────────────────────────────────┐
  │ 🖼️ [GIF preview thumbnail — 80x80px]   │
  │                                         │
  │ This GIF means:                         │
  │ 🟡 "skill issue"                        │  ← brainrot_meaning
  │                                         │
  │ ↓ In formal English                     │
  │ 🟢 "This outcome is a result of your    │
  │     own lack of ability, not an         │
  │     external problem worth addressing." │
  │                                         │
  │ Confidence: 91%                         │
  │ [📋 Copy Explanation] [✕ Close]         │
  └─────────────────────────────────────────┘

Note: The "Reply in Brainrot" button is NOT shown for image results 
because the user cannot paste a GIF via the extension into a text 
field. Only the copy explanation action is relevant.

---

### Database Schema Addition

#### In database.py — add new table:

class VerifiedImageBrainrot(Base):
    """
    Staging table for low-confidence image classifications.
    Fed into future multimodal retraining pipeline.
    """
    __tablename__ = "verified_image_brainrot"
    
    id               : int       # primary key, autoincrement
    source_url       : str       # original image/GIF URL
    media_type       : str       # image/gif, image/jpeg, etc.
    agent_meaning    : str       # what the agent thought it meant
    confidence       : float     # agent confidence score
    human_verified   : bool      # default False, updated by review
    correct_meaning  : str       # nullable, filled after human review
    timestamp        : datetime  # UTC, server default

---

### What NOT to Do

- Do not attempt to run vision inference locally on the 
  fine-tuned Llama/Mistral model — it is text-only. 
  Vision MUST go through the external API.
- Do not send images larger than 5MB to the API — 
  validate and reject with a clear user-facing error in the bubble.
- Do not treat every GIF on the page as a candidate — 
  the isMemeCandidate pre-filter is mandatory to avoid 
  unnecessary API spend.
- Do not block the page's own image loading or interfere 
  with img element event handlers already set by the page.
- Do not cache image analysis results by URL alone — 
  the same URL can host rotating GIF content 
  (e.g., Tenor random endpoints).
- Do not show the "Reply in Brainrot" UI for image-triggered results.

---

### Final Expected Capability After This Upgrade

Text trigger:
  User highlights "no cap bro was built different fr fr"
  → Pet translates to formal English + sentiment

Image/GIF trigger:
  User hovers over a "skill issue" GIF for 600ms
  → Pet explains: "This GIF communicates that the problem
    described is a direct result of the recipient's own 
    lack of competence."
  → Confidence: 91%

Both triggers use the same pet bubble UI, same PostgreSQL 
active learning staging, and same confidence threshold logic.