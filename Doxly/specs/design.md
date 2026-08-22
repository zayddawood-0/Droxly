# Doxly — Design Philosophy & Brand Identity

> **Status of this document:** Source of truth for Doxly's product design philosophy, brand identity, and UX/interaction *principles*. It answers "what should this product feel like, and why" — the brief a product designer writes before opening a design tool. It does **not** define tokens, components, layouts, or page-by-page specs; that enforceable visual system lives in `specs/ui-ux.md`. Where this file says "documents feel like X," `ui-ux.md` says "therefore the document card uses this spacing, this color, this state." If the two ever appear to conflict, `ui-ux.md` wins on the specific pixel/token decision, but it must be revised if it violates a principle stated here — see §8.
>
> Requirement IDs (`FR-xxx`, `NFR-xxx`) referenced below are defined in `specs/requirements.md`. Architectural decisions referenced below are defined in `specs/decisions.md`.

---

## 1. Brand Identity

### 1.1 Name & tagline

- **Name:** Doxly
- **Tagline:** *Your docs, but smarter.*
- **Category:** AI-Powered Document Intelligence Platform

### 1.2 Positioning statement

Doxly is the place Gen Z-leaning students, developers, researchers, freelancers, and young professionals bring a document when they want to stop reading it and start *using* it. Where legacy document management tools organize files, Doxly understands them — it reads, answers, extracts, compares, and finds, so the human doesn't have to do the tedious part. Doxly is not enterprise DMS software wearing an AI badge; it is an AI-first product that happens to store files.

### 1.3 Personality traits

Doxly is:

- **Modern** — feels like it was built this year, not ported from 2012 enterprise software.
- **Intelligent** — the AI is genuinely capable, not a gimmick bolted onto a file manager.
- **Minimal** — every screen shows exactly what's needed and nothing performing "seriousness."
- **Friendly** — approachable and human, never cold or corporate.
- **Futuristic** — feels a step ahead, but grounded — never sci-fi cosplay.
- **Confident** — states things plainly; doesn't hedge with corporate qualifiers.
- **Approachable** — a first-year student and a startup founder should both feel it was built for them.

Doxly is explicitly **not**: stiff, jargon-heavy, cluttered, gradient-happy, animation-for-its-own-sake, or anything that reads as "legacy enterprise document management."

### 1.4 Brand voice — how Doxly talks

Doxly's UI copy, marketing copy, and AI responses all share one voice, calibrated by context (see §4). The voice rules:

1. **Confident but not arrogant.** Say what happened plainly: "Summary ready." not "We have successfully generated your summary for you!" Confidence also means owning limits honestly (§2.6): "I couldn't find that in this document" is a confident sentence, not a weak one.
2. **Helpful but not robotic.** Copy sounds like a sharp friend who's good at this, not a terms-of-service document. Contractions are fine. Personality is fine in small doses. Never sound like a form letter.
3. **Concise.** If a sentence can lose a clause without losing meaning, cut it. Doxly respects the reader's time as much as the product respects their time.
4. **Plain language over jargon.** "We couldn't read this file" beats "Extraction pipeline returned a non-zero exit status." Technical precision is for logs, not for users.
5. **Never condescending.** Doxly explains without talking down, especially to a first-time user who doesn't yet know what "RAG" or "embeddings" means and never needs to.

---

## 2. Design Principles

These are the product's design commitments — the things that should be true on every screen, regardless of feature. Each ties to a concrete implication for how a screen should look and behave, not just an abstract value.

1. **Minimal by default.** A screen earns every element on it. Implication: new features default to hidden/secondary until proven necessary; whitespace is a design choice, not empty space to be filled. `ui-ux.md` owns the resulting spacing/density tokens.
2. **AI is a collaborator, not a black box.** The user should always be able to see *why* the AI said something. Implication: every AI-generated answer that draws on document content shows its citations inline, visibly, by default — never hidden behind a "show sources" toggle the user has to find. This is a direct product implication of `FR-RAG-002` (citation grounding) and `FR-AI-004` (graceful "I don't know" instead of fabricating): if the AI can't ground a claim, the UI must make that visible rather than smoothing it over with confident-sounding prose. Trust is the product's real differentiator, not just a UX nicety — a competitor with a smarter model but opaque answers is less trustworthy than Doxly with a transparent one.
3. **Speed is a feature.** Waiting kills trust in an AI product faster than almost anything else. Implication: every screen has a fast perceived path to *something visible* — skeleton states, streaming tokens (`FR-AI-005`), progressive results — rather than a blank screen until everything is ready.
4. **Never make the user feel dumb.** Doxly's audience ranges from a first-year student to a founder — nobody should need a manual. Implication: empty states teach by example, errors explain the fix not just the failure, and no screen assumes prior familiarity with AI/RAG terminology.
5. **Progressive disclosure over dense forms.** Complexity is revealed only when the user asks for it. Implication: default flows (upload → ask a question) are one or two taps; power-user configuration (custom extraction schemas, comparison options) sits one layer deeper, never blocking the simple path.
6. **Show, don't perform.** Motion, gradients, and decoration are used only when they communicate something (a state changed, a relationship exists) — never as ambient decoration that adds visual noise without adding meaning. This directly protects principle 1 and keeps Doxly from drifting toward the "over-designed AI product" aesthetic it's explicitly trying to avoid.
7. **Consistency compounds trust.** The same action should look and behave the same way everywhere it appears (a delete button, a citation chip, a loading state). This is what makes speed and confidence *feel* real across the whole product rather than screen-by-screen.

---

## 3. UX Principles

### 3.1 Clarity over cleverness

If a clever interaction requires an explanation, it's the wrong interaction. Doxly favors the obvious control over the delightful-but-confusing one. Cleverness is welcome in what the AI can *do* (extraction, comparison, semantic search) — not in how the user has to figure out *how* to use it.

### 3.2 Feedback for every action

No user action should ever leave the user wondering whether it worked. Every feature is expected to define, at minimum, four states: **loading**, **empty**, **error**, and **success** — this is a baseline expectation for every screen and every AI operation, not an optional polish pass. The specific visual treatment of each state (skeletons, spinners, illustrations, copy) is defined per-page in `ui-ux.md`; this document establishes that the four-state contract is non-negotiable everywhere, including AI operations that take real time (processing, extraction, comparison — see `FR-DOC-008`).

### 3.3 Forgiving interactions

Mistakes should be cheap. Two patterns govern this:

- **Undo over "are you sure?"** where the action is reversible or low-stakes (renaming a document, removing a tag) — no confirmation dialog, just an undo affordance after the fact.
- **Explicit confirmation for destructive, irreversible actions** — deleting a document (`FR-DOC-005`) or deleting an account (`FR-USER-002`). Account deletion in particular warrants a *typed* confirmation (per `FR-USER-002`'s acceptance criteria), because its blast radius is total and irreversible; document deletion warrants a confirmation step but not typed confirmation, because its blast radius is smaller and the action is common enough that over-friction would erode trust in the product's speed.

The line between these two patterns is deliberate: over-confirming reversible actions trains users to blindly click through every dialog, which defeats the purpose of confirmation entirely by the time it matters.

### 3.4 Accessibility as a default, not an afterthought

Accessibility is not a pass done at the end — it is a default assumption behind every design decision, matching `NFR-A11Y-001` (WCAG 2.1 AA across auth, upload, chat, search: keyboard navigable, screen-reader labeled, sufficient contrast) and `NFR-A11Y-002` (respecting reduced-motion preferences). Practically: no interaction is mouse-only, no state is communicated by color alone, and no animation is required to understand what happened. The token-level contrast ratios, focus states, and ARIA patterns that implement this are specified in `ui-ux.md`; this document establishes that accessibility is a first-class design constraint, evaluated at design time, not a remediation task.

---

## 4. Product Personality in Practice

One brand voice (§1.4), three contexts, three calibrations:

### 4.1 The AI assistant's voice (chat responses)

Grounded, precise, and citation-first. The assistant speaks like a sharp, well-prepared colleague who has actually read the document — not like a generic chatbot performing enthusiasm. It states what it found, points to where it found it, and says plainly when it didn't find something (`FR-AI-004`). It doesn't apologize excessively, doesn't over-hedge with disclaimers on every sentence, and doesn't pad answers to sound more thorough than the source material supports.

### 4.2 Marketing / landing copy

Confident and benefit-first, speaking to what the user gets to stop doing ("Stop re-reading contracts for the one clause that matters") rather than what the product technically does ("leverages LLM-powered semantic retrieval"). Energetic without hype-speak — no "revolutionary," no "game-changing," no exclamation-point stacking. It should read like a product a discerning developer would trust, not like a SaaS landing page generator's default output.

### 4.3 Error messages

Calm, specific, and actionable — never alarming, never blaming the user, never exposing internals (consistent with `NFR-SEC-009`, which bars stack traces/internal detail from client-facing errors). An error message names what happened in plain language and, wherever possible, what to do next: "This file looks like a scanned image — Doxly can't read text from it yet" beats "Processing failed" beats a raw exception string. The tone stays the same brand voice as chat and marketing copy — just quieter and more direct, because a user seeing an error is already mildly frustrated and does not need personality performed at them.

All three registers are recognizably the same brand at different volumes: precise-and-grounded in chat, confident-and-warm in marketing, calm-and-clear in errors.

---

## 5. User Journey

The core product loop is **Upload → Understand → Ask → Extract → Compare → Search → Act**. Not every user touches every step every session, but the loop is designed so each step lowers the emotional cost of the next one — the product's job is to move the user from *uncertainty* to *clarity* to *confidence*, as quickly and legibly as possible.

### 5.1 Persona: Maya, university student prepping for an exam

Maya has a 40-page lecture PDF and three days before her exam. She doesn't want to read it linearly — she wants to know what's actually on the exam.

- **Uncertainty:** She uploads the PDF unsure whether this will actually save her time or just be "another tool to learn." The upload has to feel instant and low-commitment — no setup, no config screen.
- **Clarity emerging:** Doxly shows it's processing (not stuck), then she asks "what are the key concepts in chapter 3?" and gets a grounded, cited answer she can tap to verify against the source page. Seeing the citation land exactly where she expects builds trust fast — this is the moment `FR-RAG-002` is a product experience, not a backend detail.
- **Confidence:** By her third question, she's not double-checking every citation anymore — she trusts the pattern. She generates a bullet-point summary (`FR-SUM-001`) to review the night before. The emotional arc closes on *"I know what's actually in this document"* rather than *"I re-read a PDF."*

### 5.2 Persona: Jordan, freelancer reviewing a contract

Jordan gets a client contract and needs to know, fast, whether anything in it is unusual before signing.

- **Uncertainty:** Contracts are intimidating even to freelancers who've read many of them — the fear is missing something buried in clause 14.
- **Clarity emerging:** Jordan uploads the contract and asks Doxly to extract key terms (payment terms, termination clause, IP ownership) using a preset extraction template (`FR-EXT-002`). Each extracted field shows its source citation and a confidence signal, and any field Doxly couldn't find comes back honestly flagged as not found (`FR-EXT-003`) rather than guessed.
- **Confidence:** Jordan compares this contract against a previous one from the same client (`FR-COMP-001`) and sees exactly what changed, classified by type — not a wall of red/green diff noise. The arc closes on *"I know what I'm signing"* — confidence earned through visible, checkable work, not blind trust in a black box.

### 5.3 Persona: Priya, developer parsing API docs

Priya just joined a project with a large, unfamiliar third-party API reference and needs to integrate against it today.

- **Uncertainty:** She doesn't know the doc's structure yet and doesn't want to read it end-to-end just to find the auth flow.
- **Clarity emerging:** She uploads the docs and asks direct implementation questions ("how does pagination work on the /users endpoint?"). Streaming responses (`FR-AI-005`) mean she's reading the start of the answer before the model has finished — the product feels fast, which matters more to a developer's trust than almost anything else.
- **Confidence:** She uses global search (`FR-SEARCH-001`) to jump straight to a specific endpoint later in the day without re-asking the assistant, because now she understands the doc's shape well enough to search it directly. The arc closes on *"I don't need the AI to hold my hand anymore, and that's the product working correctly"* — Doxly's goal is to make itself less necessary over the course of a session as the user's own understanding compounds, not to maximize engagement for its own sake.

---

## 6. Information Architecture

Doxly's mental model has one core object and a small set of things you *do* to or across it. Everything else in the navigation is a lens onto that object.

```
Doxly
├─ Documents (the core object)
│   ├─ Upload
│   ├─ View / read
│   ├─ Metadata (tags, status, size, dates)
│   └─ Processing status (queued → extracting → chunking → embedding → ready | failed)
│
├─ Things you DO to a document (or a set of documents)
│   ├─ Ask   → AI Chat (Q&A grounded in one document, or across many)
│   ├─ Understand → Summarize (brief / detailed / bullet points)
│   ├─ Extract → Structured field extraction (presets or custom schema)
│   └─ Compare → Two documents (or two versions) aligned and diffed
│
├─ Things you DO across all documents
│   ├─ Search → Global hybrid (keyword + semantic) search
│   └─ Analytics → Usage insights (documents processed, storage, AI usage)
│
├─ Dashboard — the entry point / overview
│   └─ Surfaces: recent documents, processing status, quick actions into
│      Ask / Extract / Compare / Search, usage snapshot
│
└─ Settings — account, plan/usage, security/sessions, notifications
```

**Reading this model:** "Documents" is the noun; "Chat," "Summarize," "Extract," "Compare," and "Search" are verbs applied to that noun (or a collection of it). The Dashboard is not a separate concept — it's the overview lens that surfaces the noun and offers shortcuts into the verbs. This mental model is why the top-level navigation (Dashboard, Documents, AI Chat, Extractions, Compare, Search, Analytics, Settings) reads as a flat list of destinations but *feels* coherent: every destination other than Dashboard and Settings is either "the documents themselves" or "a thing you can do to them." The literal page layout, navigation component, and visual hierarchy that implement this model live in `specs/ui-ux.md`; this section only establishes the concept it must express.

---

## 7. Interaction Pattern Principles

These are principles, not component specs — the enforceable component-level patterns (exact states, animations, spacing) live in `ui-ux.md`. These principles are what that system must uphold:

1. **AI actions always show a visible processing state, never a silent spinner with no context.** "Reading page 12 of 40" beats a bare spinner beats nothing. The user should always have a rough sense of what's happening and roughly how long it will take.
2. **Citations are always inline and clickable, never a footnote you have to hunt for.** A citation is part of the answer's primary reading path, not an appendix — this is the direct interaction-level expression of Design Principle 2 (§2).
3. **Destructive actions require explicit confirmation; non-destructive actions never require confirmation.** Confirmation is a scarce resource — spend it only where the cost of a mistake is real (§3.3). An interaction pattern that confirms everything trains users to stop reading confirmations, which defeats the point exactly when it matters most (account deletion).
4. **Every AI-generated result is visibly distinguishable from user-authored content.** A summary, an extracted field, a comparison verdict — all carry a clear signal that they were generated, so the user always knows what came from the source document versus what came from the model's interpretation of it.
5. **Streaming over waiting, wherever the underlying operation allows it.** If tokens can arrive progressively, they should — perceived speed is real speed to the user (Design Principle 3).
6. **Failure states explain what happened and what's next, never a dead end.** A failed upload, a failed extraction field, a failed comparison — each surfaces a plain-language reason and, where possible, a retry path (`FR-PROC-004`, `FR-PROC-005`), instead of leaving the user stuck with no next action.
7. **The interface never asks the user to do something the AI could reasonably infer.** Presets, smart defaults, and pre-filled schemas (`FR-EXT-002`) exist so the user's first interaction with a new capability is trying it, not configuring it.

---

## 8. Design Consistency Governance

`specs/ui-ux.md` is the enforceable source of truth for Doxly's actual visual design system — typography, color, spacing, elevation, motion, and the full component inventory, specified per-page and per-state. This document (`design.md`) is the philosophy that system exists to serve: the brand identity, the design and UX principles, and the interaction principles above are the standard `ui-ux.md`'s concrete decisions must uphold.

In practice, this means:

- When `ui-ux.md` specifies a token, layout, or component behavior, it wins on that specific decision — this document does not attempt to re-litigate pixel values or exact states.
- If a decision in `ui-ux.md` appears to violate a principle stated here (for example, a component that hides citations behind a secondary click, or a confirmation dialog on a non-destructive action), that is a defect in `ui-ux.md` to be revised, not a signal that this document is wrong.
- New features are designed by first checking this document for the relevant principle, then implementing it concretely in `ui-ux.md` — philosophy first, system second, in that order, every time.

---

## Changelog

- **2026-08-19** — Initial design philosophy and brand identity established during SDD initialization.
