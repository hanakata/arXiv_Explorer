# arXiv Explorer: Rolling-Window Fetcher & Knowledge Manager

An intelligent, lightweight CLI tool designed for researchers and engineers to efficiently track CS papers from arXiv, manage information lifecycle with TTL logic, and build a personalized technical glossary.



---

## Key Features

* **Rolling-Window Scanning**: Fetches the latest CS papers within a 7-day sliding window to ensure no relevant research is missed.
* **Intelligent TTL (Time-To-Live)**: 
    * **Standard**: 7 days.
    * **Extended**: 30 days for high-priority topics (e.g., `eBPF`, `Kernel`, `Zero-copy`, `Distributed Systems`).
    * **Auto-Cleanup**: Automatic expiration management to prevent local database bloat.
* **Integrated Glossary & Annotation**: Automatically highlights registered technical terms in paper summaries and provides footnoted definitions using a custom-built glossary engine.
* **Read Tracking**: Distinguishes between `unread` and `read` papers, featuring a visual bar chart of your reading backlog.
* **Production-Ready Persistence**: Powered by SQLite with **WAL (Write-Ahead Logging)** mode for concurrent access and data integrity.

---

## 🛠 Tech Stack

* **Runtime**: Python 3.10+
* **Data Validation**: `Pydantic` (Strict schema enforcement)
* **Interface**: `Rich` (High-performance terminal UI)
* **Data Store**: `SQLite` (WAL mode enabled)
* **API**: `arxiv` (Official API wrapper with rate-limiting)

---

## Directory Structure

```text
.
├── src/
│   ├── main.py          # Orchestration (Fetch, Cleanup, Entry point)
│   ├── database.py      # Persistence layer (Schema, WAL, CRUD)
│   ├── fetcher.py       # arXiv API client with date-sentinel logic
│   ├── models.py        # Pydantic data models
│   ├── viewer.py        # Terminal UI & Annotation engine
│   └── glossary.py      # CLI for glossary management
├── configs/
│   └── keywords.yaml    # Config for TTL-extension keywords
└── data/
    └── archive.db       # SQLite DB (Local persistent store)
```

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/arxiv-explorer.git
   cd arxiv-explorer
   ```

2. **Install dependencies:**
   ```bash
   pip install arxiv pydantic rich pyyaml
   ```

3. **Initialize the database:**
   ```bash
   python -c "from src.database import init_db; init_db()"
   ```

---

## Usage

### 1. Ingest Latest Papers
Fetch new papers and perform TTL cleanup. The fetcher respects a 3-second delay to comply with arXiv API politeness.
```bash
python src/main.py
```

### 2. Reading Interface
Display unread papers. Technical terms from your glossary will be automatically highlighted and footnoted.
```bash
# Show unread papers (default)
python src/viewer.py show --days 7 --limit 10

# Show both read and unread papers
python src/viewer.py show --all
```

### 3. Backlog Analytics
Visualize your unread paper counts over the last week.
```bash
python src/viewer.py unread
```

### 4. Glossary Management
Build your personal knowledge base.
```bash
# Add a term
python src/glossary.py add "VLA" --def "Vision-Language-Action model"

# Update with aliases (supports case-insensitive matching)
python src/glossary.py update "VLA" --aliases "VLA model, Vision-Language-Action"

# List all terms
python src/glossary.py list
```

---

## Design Philosophies

* **API Politeness**: Implements mandatory sleep intervals between requests.
* **No-Waste Storage**: TTL-based deletion ensures that only relevant or "pinned" high-interest papers occupy disk space.
* **Atomic Operations**: Uses SQLite's `INSERT OR IGNORE` and transaction-safe migrations.
* **Extensibility**: Schema-first design via Pydantic facilitates easy integration with LLM-based summarization or RAG pipelines in the future.

---

## ️ License
MIT License. See `LICENSE` for more information.

