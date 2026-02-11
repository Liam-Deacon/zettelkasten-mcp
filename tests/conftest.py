"""Common test fixtures for the Zettelkasten MCP server."""

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from zettelkasten_mcp.config import config
from zettelkasten_mcp.models.db_models import Base
from zettelkasten_mcp.services.zettel_service import ZettelService
from zettelkasten_mcp.storage.note_repository import NoteRepository


@pytest.fixture
def temp_dirs():
    """Create temporary directories for notes and database."""
    with tempfile.TemporaryDirectory() as notes_dir:
        with tempfile.TemporaryDirectory() as db_dir:
            yield Path(notes_dir), Path(db_dir)


@pytest.fixture
def test_config(temp_dirs):
    """Configure with test paths."""
    notes_dir, db_dir = temp_dirs
    database_path = db_dir / "test_zettelkasten.db"
    # Save original config values
    original_notes_dir = config.notes_dir
    original_database_value = config.database
    # Update config for tests
    config.notes_dir = notes_dir
    config.database = str(database_path)
    yield config
    # Restore original config
    config.notes_dir = original_notes_dir
    config.database = original_database_value


@pytest.fixture
def note_repository(test_config):
    """Create a test note repository."""
    # Create tables
    # Create sync engine to initialize tables
    engine = create_engine(test_config.get_db_url())
    Base.metadata.create_all(engine)
    engine.dispose()
    # Create repository
    repository = NoteRepository(notes_dir=test_config.notes_dir)
    # Initialize is handled in constructor
    yield repository


@pytest.fixture
def zettel_service(note_repository):
    """Create a test ZettelService."""
    service = ZettelService(repository=note_repository)
    # Initialize is handled in constructor
    yield service
