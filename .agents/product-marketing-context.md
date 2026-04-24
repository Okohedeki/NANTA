# Product Marketing Context

*Last updated: 2026-04-23 (V1 auto-draft from README + recent session work — needs human review)*

> **NOTE TO REVIEWER (Edeki):** This is the AI's first pass. Skim each section and tell me what's wrong, missing, or off-tone. The bits I'm least confident about are flagged with `[?]`.

---

## Product Overview

**One-liner:**
NANTA is a personal knowledge engine that turns the things you save into a self-researching, self-narrating library.

**What it does:**
You forward a URL, audio, video, or PDF from Telegram or Discord. NANTA extracts entities, relationships, and a 3–5 paragraph summary into a searchable knowledge graph. From there it goes further than other tools: it auto-categorizes everything into 12 themed buckets, opens a "research thread" on each article that periodically searches the web for related new sources (text, news, video), generates podcast briefings on hot graph topics with a local neural voice, and exposes the whole thing through a desktop graph viewer and a CLI built for AI coding agents.

**Product category:**
Personal knowledge management (PKM) / second brain — but the marketing angle should reposition this as **"AI research analyst you self-host"** since pure PKM is a saturated shelf.

**Product type:**
Open-source desktop app (Python + FastAPI + pywebview) with optional Telegram/Discord ingestion bots. Windows installer + run-from-source. Local-first SQLite knowledge graph at `%APPDATA%\NANTA\knowledge.db`.

**Business model:**
Free, MIT-licensed, self-hosted. No SaaS layer today. `[?]` Open question: do you want to keep it 100% free/OSS, or add a hosted/managed tier later?

---

## Target Audience

**Target companies:**
N/A — individual prosumer / dev tool. `[?]` But the CLI's "for AI agents" framing suggests there could be a B2B angle (devs at AI startups using it as a context store for their Claude Code workflows).

**Decision-makers:**
The user IS the decision-maker. No procurement.

**Primary use case:**
"I read/listen to too much, none of it sticks, and I never connect the dots. NANTA both stores it AND keeps researching it after I've forgotten about it."

**Jobs to be done:**
- **JTBD-1 — Capture without friction:** When I see something interesting on my phone, I want to save it in one tap so I don't lose it.
- **JTBD-2 — Stop forgetting:** When I save something, I want it summarized + connected to what I already know so future-me can find it.
- **JTBD-3 — Stay current effortlessly:** When a topic matters to me, I want my system to keep finding new stuff on it without me asking.
- **JTBD-4 — Listen back, not just read:** When I have downtime, I want a podcast briefing on what's been happening in my graph.
- **JTBD-5 — Feed AI agents the right context:** When I'm coding with Claude Code, I want a CLI that pipes my saved knowledge into prompts.

**Use cases / scenarios:**
- A solo founder collecting market intel — competitor blog posts, customer interviews, regulatory updates.
- A research-heavy professional (lawyer, analyst, journalist) who consumes 50+ articles a week and needs them tied together.
- An AI engineer who wants their Claude Code sessions to have access to their personal corpus via `nanta search "..."`.
- A polymath who reads across AI, climate, finance, and culture and wants the cross-cutting connections surfaced automatically.

---

## Personas

`[?]` This is positioned as B2C for now — single-user. Below is a single-persona model. Tell me if there's actually a B2B angle to develop.

| Persona | Cares about | Challenge | Value we promise |
|---|---|---|---|
| **The Curious Polymath** | Not losing the dots between things they read | Their bookmarks/highlights are graveyards; nothing connects | "Save once, the system keeps researching" |
| **The AI-Native Builder** | Piping their personal knowledge into AI workflows | Generic LLMs don't know what they've been reading | A CLI + local graph their agents can query |
| **The Researcher (analyst, journalist, lawyer)** | Watching evolving stories without manually re-googling | Manual literature review is a tax on every project | Auto-research threads keep topics alive 24h/7d |

---

## Problems & Pain Points

**Core problem:**
"I save a lot of stuff but nothing ever ties together, and I don't go back to it."

**Why alternatives fall short:**
- **Read-it-later apps (Pocket, Instapaper, Readwise Reader):** purely passive — they store, they don't synthesize, they don't research forward.
- **PKM tools (Obsidian, Logseq, Notion):** require manual linking. The graph is whatever YOU put in it. Auto-extraction is bolt-on at best.
- **AI assistants (ChatGPT, Claude):** stateless — they don't have your reading history. Each conversation starts cold.
- **Newsletter aggregators / Feedly:** topic-driven but not personalized to YOUR existing knowledge graph; no synthesis.

**What it costs them:**
- Hours of re-Googling things they read 3 weeks ago and half-remember.
- Missed connections — the article they read in March that would have made the conversation in October better.
- Cognitive overhead of "I should write a summary" never happening.

**Emotional tension:**
- Information FOMO ("I'm falling behind in my field").
- The shame of an untouched Obsidian vault.
- The frustration of having to brief yourself before every new project even though you've already read 50 things on the topic.

---

## Competitive Landscape

**Direct competitors (same shelf, same goal — AI-augmented PKM):**
- **Mem.ai** — falls short because it's cloud-only, expensive, no graph viewer, no podcast generation, no auto-research.
- **Notion AI** — falls short because it's a database, not a graph; no entity extraction; no proactive research.

**Secondary competitors (different category, overlapping job):**
- **Obsidian + community plugins** — falls short because manual linking is its philosophy; auto-extraction means installing 5 plugins that don't talk to each other; no podcast/audio.
- **Readwise + Reader** — falls short because it's read-it-later + highlights, not graph + research; no generation; cloud-only.
- **NotebookLM** — surprisingly close on the podcast angle — falls short because it's session-bound (you upload a few sources, get a podcast, done). NANTA is persistent and self-extending.

**Indirect competitors (different approach to the same outcome):**
- **Hiring a research assistant** — falls short on cost and latency.
- **Just a good RSS reader + your own discipline** — falls short because the discipline never happens.

---

## Differentiation

**Key differentiators:**
- **Active not passive** — auto-research threads + spider keep your knowledge growing while you sleep.
- **Generative output, not just storage** — articles, newsletters, podcasts (with AI voice) come OUT of the graph, not just summaries going IN.
- **Local-first, free TTS** — Kokoro neural voice runs on your CPU; no ElevenLabs bills.
- **Multi-input ingestion** — Telegram/Discord bots mean save-from-anywhere. Audio/video/PDF all transcribed locally with Whisper.
- **CLI-as-tool for AI agents** — `nanta search` / `nanta digest` are designed for Claude Code/Aider/Cursor to call.
- **Open-source, self-hosted** — your graph is YOUR file on YOUR disk.

**How we do it differently:**
Most PKM tools treat your knowledge as an inert database. NANTA treats it as a *living organism* — it extracts, connects, researches, narrates, and re-categorizes itself.

**Why that's better:**
The user's job isn't to maintain a knowledge base. The user's job is to be interesting and capable. NANTA does the maintenance.

**Why customers choose us:**
- "It's the only tool where saving a link actually leads to something useful happening later."
- "I get a podcast every 24h about whatever I've been reading most about — without asking."
- "It's the first PKM tool I've actually opened a second time."

---

## Objections

| Objection | Response |
|---|---|
| **"I already have Obsidian / Readwise / Mem."** | NANTA isn't a vault. It's an agent that *uses* a vault. You can run both — NANTA's graph lives in its own SQLite file. |
| **"I don't trust auto-categorization / auto-research to not get it wrong."** | Everything is reviewable, manually overridable, and dismissible. Auto-categories never override manual picks. Discoveries are listed before they're surfaced. |
| **"Why self-host? I want a SaaS."** | The point is your data stays yours, no monthly bill, no rate limits, no vendor lockout. If you want hands-off, the install is one `.exe`. |
| **"Will the LLM costs add up?"** | You can use Ollama (free, local) for extraction. Generation uses Claude Code (your own subscription) or OpenCode. Auto-podcast TTS is free local Kokoro. The "interesting bits" budget is yours to set. |
| **"Telegram/Discord — really?"** | Those are the ingestion entry points. The thinking happens in the desktop app + CLI. They were chosen because they're already on your phone. |

**Anti-persona:**
- People who want a hosted SaaS with a customer-success rep.
- People who want their notes/data in someone else's cloud.
- People who don't read or save much (low input volume → graph stays sparse → spider has nothing to chew on).
- Pure casual users who'd be happier with Apple Notes.

---

## Switching Dynamics (JTBD Four Forces)

**Push (away from current):**
- "My Obsidian vault is a graveyard."
- "I bookmark articles I never re-open."
- "Readwise gives me highlights but never connects them."
- "ChatGPT doesn't know what I've been reading."

**Pull (toward NANTA):**
- "An agent that actually does something with what I save."
- "A daily/weekly podcast about my own knowledge graph."
- "A CLI my AI coding tools can hit."
- "Free local AI voice — no ElevenLabs subscription."

**Habit (what keeps them stuck):**
- The cognitive cost of moving notes/highlights to a new system.
- "I'll get organized one day" (they won't, but the existing tool stays open).
- Sunk-cost on existing setup.

**Anxiety (what worries them about switching):**
- "Another tool I'll abandon in two weeks."
- "What if the AI hallucinates my notes?"
- "What if my graph data gets locked into another proprietary format?" (NANTA: SQLite, fully exportable.)
- Setup pain — Telegram bot tokens, choosing a provider, etc.

---

## Customer Language

`[?]` These are the AI's guesses. Replace with verbatim quotes from real users when you have them.

**How they describe the problem:**
- "I save a million things and never read them."
- "My second brain is more like a black hole."
- "I read a great article, then can't find it three weeks later."
- "I want my notes to actually do something."
- "I'm drowning in tabs."

**How they describe NANTA (aspirational):**
- "It's like Obsidian but it does its own homework."
- "I just throw links at it and it makes a podcast for me."
- "It's the first knowledge tool I haven't given up on."
- "It feels like having a research analyst."

**Words to use:**
- *Evolving thread, spider, graph, auto-research, briefing, save-and-forget, local-first, your private analyst.*

**Words to avoid:**
- "Second brain" (cliché).
- "AI-powered" (everything is — meaningless).
- "Productivity" (overpromised, underdelivered everywhere).
- "Notes app" (too humble for what this is).
- "Knowledge management" (too enterprise, too dry).

**Glossary:**
| Term | Meaning |
|---|---|
| Source | One ingested item: an article, video, tweet, PDF, voice note. |
| Entity | A thing extracted from a source (person, org, concept, place, etc.). |
| Graph neighbor | Two entities are neighbors if they appear in at least one shared source. |
| Evolving thread | A research thread attached to a generated piece — keeps polling for related new sources. |
| Spider research | Graph-driven topic research: the system picks a hot graph topic and researches it without you asking. |
| Auto-podcast | Sparse, automated podcast briefing on the most interesting recent topic in your graph. |
| Discovery | A new source brought in by a research poll, linked back to its originating thread or topic. |
| Hot topic | An entity ranked by `3 × recent_7d + neighbors + 0.5 × total_sources`. |

---

## Brand Voice

**Tone:**
- Confident, terse, slightly dry.
- Treats the reader like a peer, not a beginner. Skips boilerplate.
- Honest about tradeoffs (local-first means YOU run it; sparse means it might not generate every day).

**Style:**
- Short sentences.
- Concrete verbs (NANTA *researches*, *spiders*, *briefs* — not *helps you with*).
- Lists > paragraphs when explaining features.
- No emoji unless used for a real signal.

**Personality:**
- Curious
- Patient (sparse, doesn't spam)
- Self-directed (auto-research, auto-podcast)
- Quietly opinionated (12 opinionated default categories, picked voice, picked search strategy)
- Built-by-one-person, not VC-bloated

---

## Proof Points

`[?]` Mostly N/A pre-launch. Below is what's CLAIMABLE today; testimonial slots are placeholders.

**Metrics:**
- 100% local-first (Kokoro TTS, Ollama provider, SQLite graph).
- ~336 MB Kokoro model download is the only network dependency for TTS.
- 12 default categories, automatic.
- Sparse cadences: 1 spider research / 6h, 1 auto-podcast / 24h.
- 5 default URL ingestion strategies (yt-dlp, Whisper, trafilatura, fxtwitter, Reddit JSON, PyMuPDF).

**Customers / logos:**
- N/A pre-launch.

**Testimonials:**
- *(none yet — collect from early users)*

**Value themes:**
| Theme | Proof |
|---|---|
| Active, not passive | Auto-research threads + 6h spider + 24h auto-podcast all run without user action. |
| Local-first, no bills | Kokoro TTS local; Ollama provider local; SQLite local. |
| Multi-input save | Telegram + Discord + CLI + desktop UI — 4 ingestion surfaces. |
| Generative output | Articles, newsletters, podcasts come OUT of the graph; voice is real audio. |
| Open + scriptable | MIT license. CLI designed as a tool for AI coding agents. |

---

## Goals

`[?]` Need your input on these.

**Business goal:**
- Likely: build an audience of self-hosters / dev-curious knowledge workers who eventually want a hosted version. OR: keep it pure OSS and grow the contributor base.

**Conversion action:**
- Today: download the Windows installer OR `git clone && python launcher.py`.
- Stretch: configure a Telegram bot token (the activation moment — the first save).

**Current metrics:**
- Unknown — no analytics in the app today. Worth adding minimal anonymous opt-in pings (downloads, ingest count) before doing real positioning work.

---

## Open questions for you to answer

1. **Business model:** stay free OSS, or add a hosted tier eventually?
2. **B2B angle:** is "knowledge layer for Claude Code teams" worth pursuing, or pure prosumer?
3. **Default ICP:** which of the three personas should marketing focus on first — Polymath, AI-Native Builder, or Researcher?
4. **Anti-position:** which competitor do you most want NANTA to be defined against in copy? (Obsidian? Readwise? NotebookLM?)
5. **Tagline test:** does *"Save once. Your knowledge keeps researching itself."* land — or do you have a better candidate?
