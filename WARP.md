# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Zettelkasten MCP Server is a Model Context Protocol (MCP) server implementing the Zettelkasten knowledge management methodology. It allows Claude and other MCP-compatible clients to create, link, explore, and synthesize atomic notes.

## Common Commands

### Development Environment

```bash
# Setup virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync --all-extras

# Install dev dependencies only
uv add "mcp[cli]"
```

### Running the Server

```bash
# Run with default configuration
python -m zettelkasten_mcp

# Run with explicit configuration
python -m zettelkasten_mcp --notes-dir ./data/notes --database ./data/db/zettelkasten.db

# Run with PostgreSQL
python -m zettelkasten_mcp --notes-dir ./data/notes \
  --database postgresql+psycopg://user:password@localhost:5432/zettelkasten

# Run Smithery development server with playground
uv run playground
# or
python -m smithery.cli.playground

# Run Smithery development server
uv run dev
# or
python -m smithery.cli.dev
```

### Testing

```bash
# Run all tests
uv run pytest -v tests/

# Run tests with coverage report
uv run pytest --cov=zettelkasten_mcp --cov-report=term-missing tests/

# Run specific test file
uv run pytest -v tests/test_models.py

# Run specific test class
uv run pytest -v tests/test_models.py::TestNoteModel

# Run specific test function
uv run pytest -v tests/test_models.py::TestNoteModel::test_note_validation
```

### Code Quality

```bash
# Format code with black
black src/ tests/

# Sort imports with isort
isort src/ tests/

# Type check with mypy
mypy src/

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run pre-commit on all files
pre-commit run --all-files
```

## Architecture

### Layered Architecture

The codebase follows a clean layered architecture:

1. **Models Layer** (`src/zettelkasten_mcp/models/`)
   - `schema.py`: Pydantic models for domain entities (Note, Link, Tag, NoteType, LinkType)
   - `db_models.py`: SQLAlchemy ORM models for database persistence
   - Notes use unique timestamp-based IDs with nanosecond precision (`generate_id()`)

2. **Storage Layer** (`src/zettelkasten_mcp/storage/`)
   - `note_repository.py`: Implements dual storage architecture
   - `base.py`: Abstract repository interface

3. **Services Layer** (`src/zettelkasten_mcp/services/`)
   - `zettel_service.py`: Core business logic for note operations
   - `search_service.py`: Search and graph analysis operations

4. **Server Layer** (`src/zettelkasten_mcp/server/`)
   - `mcp_server.py`: FastMCP server implementation with 15 tools, 3 resources, and 3 prompts
   - Registers tools with proper annotations (readOnlyHint, destructiveHint, idempotentHint)

### Dual Storage Architecture

**Critical concept**: The system uses a dual storage approach:

1. **Markdown Files** (source of truth):
   - Stored in `notes_dir` (default: `data/notes/`)
   - Human-readable with YAML frontmatter
   - Can be edited directly in any text editor
   - Should be version controlled

2. **Database Index** (indexing layer):
   - SQLite by default, supports PostgreSQL/MySQL/SQL Server via SQLAlchemy
   - Enables efficient querying and graph traversal
   - Automatically rebuilt from Markdown files when counts don't match
   - Can be deleted and regenerated at any time

**Important**: If Markdown files are edited outside the system, run `zk_rebuild_index` tool to update the database.

### Semantic Link System

The server uses a comprehensive bidirectional link system:

- **Primary links**: `reference`, `extends`, `refines`, `contradicts`, `questions`, `supports`, `related`
- **Inverse links**: Automatically created (e.g., `extends` ↔ `extended_by`)
- Link types are semantic, not just structural
- All links stored in both Markdown (under `## Links` section) and database

### Note Types

Five note types supported:
- `fleeting`: Quick, temporary notes for capturing ideas
- `literature`: Notes from reading material
- `permanent`: Well-formulated, evergreen notes (default)
- `structure`: Index or outline notes that organize other notes
- `hub`: Entry points to the Zettelkasten on key topics

### Configuration System

Configuration is managed through `src/zettelkasten_mcp/config.py`:

- Uses Pydantic for validation
- Loads from environment variables via `.env` file
- All settings have sensible defaults
- Key settings:
  - `ZETTELKASTEN_NOTES_DIR`: Where notes are stored
  - `ZETTELKASTEN_DATABASE`: SQLite path or SQLAlchemy URL
  - `ZETTELKASTEN_LOG_LEVEL`: Logging verbosity

The `ZettelkastenConfig.get_db_url()` method normalizes database configuration to SQLAlchemy URLs.

### Smithery Deployment

The server supports deployment on Smithery:

- Uses `@smithery.server()` decorator in `create_server()` factory function
- Configuration schema defined via `ZettelkastenConfigSchema` Pydantic model
- Supports HTTP transport via `streamable-http`
- Configuration in `smithery.yaml` and `pyproject.toml`

## MCP Tools

All 15 tools are prefixed with `zk_`:

**Creation/Modification**:
- `zk_create_note`: Create new notes with title, content, type, tags
- `zk_update_note`: Update existing notes
- `zk_delete_note`: Delete notes (destructive)
- `zk_create_link`: Create semantic links between notes (supports bidirectional)
- `zk_remove_link`: Remove links (destructive)

**Retrieval**:
- `zk_get_note`: Get note by ID or title
- `zk_search_notes`: Search by content, tags, or note type
- `zk_get_linked_notes`: Find all notes connected to a specific note
- `zk_get_all_tags`: List all tags in the system

**Graph Analysis**:
- `zk_find_similar_notes`: Semantic similarity search
- `zk_find_central_notes`: Find highly connected hub notes
- `zk_find_orphaned_notes`: Find isolated notes with no connections
- `zk_list_notes_by_date`: List notes by creation/update date range

**Maintenance**:
- `zk_rebuild_index`: Rebuild database from Markdown files

## Important Patterns

### ID Generation
- IDs are timestamp-based: `YYYYMMDDTHHMMSSssssssccc`
- Thread-safe with counter for uniqueness within same microsecond
- Up to 1 billion unique IDs per second possible
- Located in `models/schema.py:generate_id()`

### Error Handling
- Service layer raises `ValueError` for domain validation errors
- Server layer uses `format_error_response()` for consistent error formatting
- Errors logged with unique error ID for traceability

### Database Backend Support
- SQLite: Default, no extra dependencies
- PostgreSQL: Install with `pip install "zettelkasten-mcp[postgresql]"`
- MySQL: Install with `pip install "zettelkasten-mcp[mysql]"`
- SQL Server: Install with `pip install "zettelkasten-mcp[sqlserver]"`

### Testing Strategy
- Tests organized by layer: models, storage, services, server, integration
- Use `conftest.py` for shared fixtures
- All tests use temporary directories and in-memory databases
- Coverage target: comprehensive coverage of all layers

## Code Style

- **Formatter**: Black (line length: 88)
- **Import sorting**: isort with black profile
- **Type checking**: mypy with strict mode (`disallow_untyped_defs`, `disallow_incomplete_defs`)
- **Pre-commit hooks**: Configured for black, isort, and mypy

All function signatures should have type hints, and all modules should have docstrings.

## Project Structure

```
src/zettelkasten_mcp/
├── models/          # Domain models (Pydantic) and DB models (SQLAlchemy)
├── storage/         # Repository pattern for data access
├── services/        # Business logic layer
├── server/          # MCP server implementation
├── config.py        # Configuration management
├── utils.py         # Utility functions
└── main.py          # Entry point

tests/               # Mirror of src structure with test files
data/
├── notes/           # Markdown note storage (source of truth)
└── db/              # SQLite database (can be regenerated)
```

## Database Schema

Key tables:
- `notes`: Stores note metadata (id, title, content, type, timestamps)
- `tags`: Stores unique tags
- `note_tags`: Many-to-many relationship between notes and tags
- `links`: Stores directed links between notes with link_type

## Prompting Guidelines

The `docs/prompts/` directory contains:
- **System prompts**: Instructions for LLM behavior with Zettelkasten
- **Chat prompts**: Templates for knowledge creation, exploration, and synthesis
- **Project knowledge**: Documentation about methodology and link types

These should be used when working with Claude to ensure effective knowledge management.

## Installation Methods

1. **Smithery**: `npx -y @smithery/cli install zettelkasten-mcp --client claude`
2. **uvx**: `uvx --from=git+https://github.com/entanglr/zettelkasten-mcp zettelkasten-mcp`
3. **Local development**: Clone repo, `uv venv`, `uv sync --all-extras`

## Version Control

- Uses Git for version control
- `.gitignore` excludes: `.venv/`, `__pycache__/`, `*.pyc`, `.mypy_cache/`, `.pytest_cache/`, `data/db/`
- Markdown notes in `data/notes/` should be committed (source of truth)
- Database files should NOT be committed (can be regenerated)
