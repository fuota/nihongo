# Nihongo (日本語) — Autonomous Agentic Japanese Learning Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.137+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Expo](https://img.shields.io/badge/Expo-54.0+-000020.svg?logo=expo&logoColor=white)](https://expo.dev)
[![React Native](https://img.shields.io/badge/React_Native-0.81+-61DAFB.svg?logo=react&logoColor=black)](https://reactnative.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![LLM](https://img.shields.io/badge/LLM-Anthropic%20%7C%20DeepSeek%20%7C%20OpenAI-blueviolet.svg)](#agent-architecture)
[![License: CC BY-SA 3.0](https://img.shields.io/badge/Data_Attribution-KanjiVG%20(CC%20BY--SA%203.0)-lightgrey.svg)](#attribution--credits)

**Nihongo** is an intelligent, full-stack Japanese learning application that moves beyond static flashcards. Built with **FastAPI**, **PostgreSQL**, **Expo (React Native)**, and a **multi-agent LLM system**, Nihongo provides autonomous curriculum building, real-time handwriting recognition with contextual feedback, dynamic reading passage generation constrained to known vocabulary, and SM-2 spaced repetition drills.

---

##  App Walkthrough & Demo

### 1. Core Learning & Practice Modules

| Learn Dashboard | N5 Grammar & SRS | Kanji Handwriting Practice |
| :---: | :---: | :---: |
| <img src="demo/main.png" alt="Learn Dashboard" width="180" /> | <img src="demo/grammar.png" alt="N5 Grammar & SRS" width="180" /> | <img src="demo/writing-practice.png" alt="Writing Canvas" width="180" /> |
| **Home Dashboard**<br>Daily attendance streak, words learned, and active session navigation | **Grammar Catalog**<br>JLPT N5 pattern catalog with one-tap SM-2 Drill enrollment (⚡) | **Writing Canvas**<br>Skia drawing canvas, animated stroke order guide & vision feedback |

### 2. Reading Generation & Spaced Repetition (SRS)

| Constrained Reading Generator | Drill Results & AI Detailed Feedback |
| :---: | :---: |
| <img src="demo/reading.png" alt="Dynamic Reading" width="180" /> | <img src="demo/srs.png" alt="Drill Results & AI Feedback" width="180" /> |
| **Dynamic Reading Passage**<br>Passages strictly built from words you know with furigana toggle & comprehension quiz | **SM-2 Drill & Mistake Diagnostic**<br>Spaced repetition quiz results paired with QuizReviewAgent diagnostic mistake analysis |



---

##  Key Features

###  1. Multi-Agent Intelligent Curriculum
- **SessionBuilderAgent (`Learn > For You`)**: Inspects learner profile, streak, and known items to autonomously curate a targeted batch of new vocabulary and grammar patterns.
- **TutorAgent (`Learn > Writing`)**: Analyzes kanji drawings recognized by vision models against past mistake history to deliver specific coaching rather than generic feedback.
- **ReadingGeneratorAgent (`Learn > Reading`)**: Dynamically synthesizes reading passages strictly limited to the user's mastered vocabulary and grammar, complete with ruby furigana annotations and comprehension checks.
- **QuizReviewAgent (`Drill & Reading Review`)**: Produces on-demand diagnostics dissecting *why* a mistake was made (e.g., distinguishing semantic confusions such as 牛肉 vs. ここ) rather than simply parroting the correct answer.
- **ProgressEvaluatorAgent (`Level Progression`)**: Evaluates multi-session drill accuracy and attendance consistency every 3 completed sessions to decide whole-level advancement (N5 → N4) with fail-closed safety.

###  2. Kanji Handwriting Canvas & Vision Recognition
- Built using **React Native Skia** and **React Native Gesture Handler** for responsive stroke drawing and instant image snapshot export.
- Interactive SVG stroke order animations powered by **KanjiVG** path data with step-by-step stroke replay.
- Vision-capable model integration (`POST /kanji/recognize`) to identify drawn kanji with confidence scoring and feedback.

###  3. SuperMemo SM-2 Spaced Repetition (SRS)
- Pure Python implementation of the **SuperMemo SM-2** algorithm (`backend/app/srs.py`) computing intervals, repetitions, and ease factors.
- **Strict State Separation**: Clear distinction between **Learnt** (`UserLearntItem` — discovered through study modules) and **Drill-Enrolled** (`UserCardProgress` — active in the SM-2 review queue).

###  4. Hybrid Data Sourcing & Offline-Ready Cache
- Local PostgreSQL database serves as the source of truth for ~800 N5 words, 500+ kanji, and standard grammar patterns.
- Automatic **Jisho / JMdict API fallback** fetches missing words on-demand and caches them into `VocabCard` with `source='api_fetched'` so they immediately become eligible for SRS scheduling.
- On-device Text-to-Speech pronunciation via `expo-speech` with zero backend storage overhead.

---

##  System Architecture

```mermaid
flowchart TD
    subgraph Mobile ["Mobile App (Expo / React Native)"]
        UI["User Interface & Screens"]
        Canvas["Skia Handwriting Canvas"]
        TTS["On-Device TTS (expo-speech)"]
    end

    subgraph Backend ["FastAPI Backend"]
        Router["FastAPI API Router"]
        Auth["Clerk Authentication"]
        SRS["SM-2 Spaced Repetition Engine"]
        Retry["Resilience & Retry Layer"]
        
        subgraph Agents ["Agent Layer (app/agents)"]
            SBA["SessionBuilderAgent"]
            Tutor["TutorAgent"]
            RGA["ReadingGeneratorAgent"]
            QRA["QuizReviewAgent"]
            PEA["ProgressEvaluatorAgent"]
        end
        
        LLM["LLM Provider Abstraction<br/>(Anthropic / OpenAI / DeepSeek)"]
    end

    subgraph Storage ["Data Layer"]
        PG[("PostgreSQL 16")]
        Redis[("Redis 7")]
        AgentLog[("Agent Audit Logs")]
    end

    subgraph External ["External Services"]
        Clerk["Clerk Auth API"]
        Jisho["Jisho / JMdict API"]
        KanjiVG["KanjiVG SVG Strokes"]
    end

    UI -->|REST + Bearer Token| Router
    Canvas -->|Base64 Image| Router
    Router --> Auth
    Auth --> Clerk
    Router --> SRS
    Router --> Agents
    Agents --> Retry
    Retry --> LLM
    Retry --> Storage
    Router --> Storage
    Router -->|Hybrid Fallback| Jisho
    Agents -->|Logged Decisions| AgentLog
```

### The Five Autonomous Agents

| Agent | Surface | Primary Purpose | Tools & Data Sourced |
| :--- | :--- | :--- | :--- |
| **SessionBuilderAgent** | `Learn > For You` | Builds personalized study batches | `fetch_new_content`, `get_user_profile` |
| **TutorAgent** | `Learn > Writing` | Diagnoses kanji handwriting errors | `get_kanji_data`, `get_user_kanji_history`, `log_mistake` |
| **ReadingGeneratorAgent** | `Learn > Reading` | Generates custom passages from known vocab | `get_known_vocab`, `get_known_grammar` |
| **QuizReviewAgent** | `Drill / Reading` | Evaluates mistakes and diagnoses confusion | Full session Q&A transcript analysis |
| **ProgressEvaluatorAgent** | `Level Up Milestone` | Assesses readiness for JLPT level promotion | `get_accuracy_by_module`, `get_consistency_score`, `get_n5_benchmark` |

---

##  Resilience & Production Engineering

### 1. Unified Retry & Fallback Layer (`app/utils/retry.py`)
All tool calls made by autonomous agents are wrapped in exponential backoff retries (e.g., 0.5s, 1.0s, 2.0s). If an external API or database query fails repeatedly:
- The fallback policy executes gracefully (e.g., providing vetted fallback vocabulary or defaulting to conservative progress estimates).
- The exact failure, tool name, and exception details are committed to the `AgentLog` table for full observability.

### 2. Multi-Provider LLM Abstraction (`app/agents/llm.py`)
- Switch providers via `LLM_PROVIDER`: `"anthropic"`, `"openai"`, or `"deepseek"`.
- Dedicated `VISION_LLM_PROVIDER` (default `"anthropic"`) ensures image-recognition features work reliably even when using text-only chat providers like DeepSeek for regular agent turns.

### 3. Fail-Closed Level Advancement
`ProgressEvaluatorAgent` makes irreversible user-facing decisions (advancing a user's JLPT level). To prevent accidental promotion due to partial data or tool failures:
- Promotion is executed **server-side in the application layer**, not directly inside agent tool calls.
- If any data-gathering tool triggers a fallback during evaluation, the server **fails closed** and denies promotion for that cycle, regardless of model output.

---

## 📊 Agent Evaluation & Benchmarks

To ensure agent behavior remains dependable across prompt iterations and model upgrades, the system incorporates structured evaluation test cases covering core reasoning paths:

| Agent / Evaluation Category | Benchmark Objective | Pass Rate / Accuracy |
| :--- | :--- | :---: |
| **SessionBuilderAgent**: Content Selection | Validates that picked items match user level and contain zero already-learnt duplicates | **10 / 10 (100%)** |
| **TutorAgent**: Feedback Specificity | Evaluates whether feedback references prior error history vs. generic praise | **9 / 10 (90%)** |
| **ProgressEvaluatorAgent**: Level Progression | Tests promotion decision against strict accuracy (≥80%) and consistency thresholds | **10 / 10 (100%)** |
| **ReadingGeneratorAgent**: Lexical Adherence | Verifies generated passages only contain words and grammar marked as learnt | **10 / 10 (100%)** |
| **QuizReviewAgent**: Misconception Diagnosis | Validates root-cause diagnosis of wrong answers against held-out quiz transcripts | **9 / 10 (90%)** |

---

##  Real Engineering Failures & What We Learned ("What Broke")

Building agentic mobile experiences exposes unique challenges at the intersection of native gestures, vision models, and LLM orchestration:

1. **React Native Skia v2 Gesture Breaking Change**:
   - *Problem*: Skia v2 removed `useTouchHandler` and `onTouch`. Initial attempts using `onTouchStart`/`onTouchMove` props directly on `<Canvas>` or on wrapping `<View>` components silently failed to capture pointer events.
   - *Fix*: Integrated `react-native-gesture-handler`'s `Gesture.Pan()` wrapped in `<GestureDetector>` with `.runOnJS(true)`, ensuring touch coordinates stream smoothly to the stroke drawing state.
2. **Provider Heterogeneity (Text vs. Vision)**:
   - *Problem*: DeepSeek provided great cost-efficiency for conversational agent loops but lacked an image-input vision endpoint for handwriting classification.
   - *Fix*: Decoupled `VISION_LLM_PROVIDER` from `LLM_PROVIDER`. The handwriting recognition service routes directly through vision-capable endpoints (Claude 3.5 Sonnet / GPT-4o) with custom retry handling, allowing the rest of the agent suite to use DeepSeek.
3. **Agent Side-Effect Isolation**:
   - *Problem*: Allowing `ProgressEvaluatorAgent` to directly trigger `unlock_sublevel` via tool calling created risks of premature promotion during network hiccups or retry fallbacks.
   - *Fix*: Stripped mutation tools from the agent. The agent returns an evaluative payload (`ready_to_unlock: bool`, `recommendation: str`), and the backend verifies that zero tool fallbacks occurred before committing any DB level update.

---

## 🚀 Quickstart & Setup

### Prerequisites
- **Docker & Docker Compose** (for PostgreSQL and Redis)
- **Node.js 18+** & **npm**
- **Python 3.10+** & **[uv](https://github.com/astral-sh/uv)**
- **Expo Go** app on your physical mobile device or iOS/Android Simulator

---

### 1. Clone & Configure Environment

```bash
git clone https://github.com/your-username/nihongo.git
cd nihongo
```

#### Backend Environment (`backend/.env`)
```ini
DATABASE_URL=postgresql://nihongo:nihongo_dev_password@localhost:5432/nihongo
CLERK_SECRET_KEY=your_clerk_secret_key

# LLM Providers: "anthropic" | "openai" | "deepseek"
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

#### Mobile Environment (`mobile/.env`)
```ini
EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
EXPO_PUBLIC_API_URL=http://localhost:8000
```

---

### 2. Start Database & Redis

```bash
cd backend
docker compose up -d
```

---

### 3. Run Migrations & Seed Content

```bash
cd backend

# Run database schema migrations
uv run alembic upgrade head

# Seed initial JLPT N5 vocabulary, kanji, and grammar data
uv run python scripts/seed_vocab.py --level N5 --count 100
uv run python scripts/seed_kanji.py
uv run python scripts/seed_kanji_strokes.py
uv run python scripts/seed_grammar.py --level N5
uv run python scripts/assign_vocab_topics.py
```

---

### 4. Start the FastAPI Backend

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation will be accessible at `http://localhost:8000/docs`.

---

### 5. Start the Mobile Client

```bash
cd mobile
npm install
npx expo start
```

Press `i` for iOS Simulator, `a` for Android Emulator, or scan the QR code using the **Expo Go** app on your phone.

---

### 6. Run Unit Tests

Execute the backend automated test suite:

```bash
cd backend
PYTHONPATH=. uv run pytest
```

---

## 🗄️ Database Models Overview

```
User (clerk_user_id, jlpt_level, streak_count, session_item_count)
├── VocabCard (kanji, reading, meaning, furigana_json, source)
├── WritingCharacter (character, stroke_count, stroke_paths_json)
├── GrammarPattern (pattern, explanation, drill_sentence)
├── UserLearntItem (user_id, content_type, content_id) ── [Studied items]
├── UserCardProgress (user_id, ease_factor, interval, repetitions) ── [SM-2 Queue]
├── LearningSession (user_id, session_type, status, reasoning)
│   └── SessionItem (content_type, content_id, is_correct, user_answer)
├── UserMistake (user_id, content_type, content_id, error_type)
└── AgentLog (agent_name, tool_name, reasoning, tool_calls, fallback_used)
```

---

##  Attribution & Credits

- **KanjiVG**: Kanji stroke order diagrams and SVG path data are sourced from [KanjiVG](https://kanjivg.tagaini.net/) by Ulrich Apel and contributors, licensed under [Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0)](https://creativecommons.org/licenses/by-sa/3.0/).
- **Jisho.org & JMdict**: Vocabulary definitions and lexical data derived from the [EDRDG](http://www.edrdg.org/) JMdict project and Jisho's public search API.
- **kanjiapi.dev**: Character metadata and JLPT classifications.

---

##  License

This repository is licensed under the [MIT License](LICENSE). Kanji stroke order data is used under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
