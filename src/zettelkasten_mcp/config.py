"""Configuration module for the Zettelkasten MCP server."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy.engine.url import make_url


def _default_database_setting() -> str:
    """Determine the default database configuration string."""
    return (
        os.getenv("ZETTELKASTEN_DATABASE")
        or os.getenv("ZETTELKASTEN_DATABASE_URL")
        or os.getenv("ZETTELKASTEN_DATABASE_PATH")
        or "data/db/zettelkasten.db"
    )


# Load environment variables
load_dotenv()


class ZettelkastenConfig(BaseModel):
    """Configuration for the Zettelkasten server."""

    # Base directory for the project
    base_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("ZETTELKASTEN_BASE_DIR") or ".")
    )
    # Storage configuration
    notes_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("ZETTELKASTEN_NOTES_DIR") or "data/notes"
        )
    )
    # Storage backend selection
    storage_backend: str = Field(
        default=os.getenv("ZETTELKASTEN_STORAGE_BACKEND", "filesystem"),
        description="Storage backend to use: filesystem (default) or mongo",
    )
    # Database configuration (path or SQLAlchemy URL)
    database: str = Field(default_factory=_default_database_setting)
    # MongoDB configuration (optional)
    mongodb_uri: str | None = Field(
        default=os.getenv("MONGODB_URI"),
        description="MongoDB connection string when using the Mongo backend",
    )
    mongodb_database: str = Field(
        default=os.getenv("MONGODB_DB") or "aam_knowledge_base",
        description="MongoDB database name when using the Mongo backend",
    )
    mongodb_collection: str = Field(
        default=os.getenv("MONGODB_COLLECTION") or "notes",
        description="MongoDB collection name when using the Mongo backend",
    )
    # Server configuration
    server_name: str = Field(
        default=os.getenv("ZETTELKASTEN_SERVER_NAME", "zettelkasten-mcp")
    )
    server_version: str = Field(default="1.2.1")
    # Date format for ID generation (using ISO format for timestamps)
    id_date_format: str = Field(default="%Y%m%dT%H%M%S")
    # Default note template
    default_note_template: str = Field(
        default=(
            "# {title}\n\n"
            "## Metadata\n"
            "- Created: {created_at}\n"
            "- Tags: {tags}\n\n"
            "## Content\n\n"
            "{content}\n\n"
            "## Links\n"
            "{links}\n"
        )
    )

    def get_absolute_path(self, path: Path) -> Path:
        """Convert a relative path to an absolute path based on base_dir."""
        if path.is_absolute():
            return path
        return self.base_dir / path

    def _is_database_url(self) -> bool:
        """Return True when the database setting looks like a SQLAlchemy URL."""
        value = (self.database or "").strip()
        return "://" in value

    def _ensure_sqlite_directory(self, db_url: str) -> None:
        """Ensure directories exist for SQLite URLs."""
        try:
            url = make_url(db_url)
        except Exception:
            return

        if url.get_backend_name() != "sqlite" or not url.database:
            return

        db_path = Path(url.database)
        if not db_path.is_absolute():
            db_path = self.get_absolute_path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_db_url(self) -> str:
        """Return a SQLAlchemy-compatible database URL."""
        if self._is_database_url():
            url = make_url(self.database)
            if (
                url.get_backend_name() == "sqlite"
                and url.database
                and url.database != ":memory:"
            ):
                db_path = Path(url.database)
                if not db_path.is_absolute():
                    db_path = self.get_absolute_path(db_path)
                url = url.set(database=str(db_path))
            db_url = url.render_as_string(hide_password=False)
        else:
            db_path = self.get_absolute_path(Path(self.database))
            db_url = f"sqlite:///{db_path}"

        self._ensure_sqlite_directory(db_url)
        return db_url

    def uses_sqlite(self) -> bool:
        """Return True if the database backend is SQLite."""
        try:
            return make_url(self.get_db_url()).get_backend_name() == "sqlite"
        except Exception:
            return self.get_db_url().startswith("sqlite:")

    def use_mongodb(self) -> bool:
        """Return True when MongoDB backend is configured."""
        return str(self.storage_backend).lower() == "mongo" and bool(self.mongodb_uri)


# Create a global config instance
config = ZettelkastenConfig()
