"""Tests for the configuration module."""

from pathlib import Path

from sqlalchemy.engine.url import make_url

from zettelkasten_mcp.config import ZettelkastenConfig


def test_config_defaults_to_sqlite(tmp_path):
    cfg = ZettelkastenConfig(
        base_dir=tmp_path,
        notes_dir=Path("notes"),
        database="db/test.db",
    )

    db_url = cfg.get_db_url()

    assert cfg.uses_sqlite()
    assert db_url == f"sqlite:///{tmp_path / 'db' / 'test.db'}"
    assert (tmp_path / "db").exists()


def test_config_uses_database_url_when_provided(tmp_path):
    database_url = "postgresql+psycopg://user:pass@localhost:5432/zettelkasten"

    cfg = ZettelkastenConfig(
        base_dir=tmp_path,
        notes_dir=Path("notes"),
        database=database_url,
    )

    assert not cfg.uses_sqlite()
    assert cfg.get_db_url() == database_url
    assert not (tmp_path / "db").exists()


def test_config_handles_mysql_url(tmp_path):
    database_url = "mysql+pymysql://user:pass@localhost:3306/zettelkasten"

    cfg = ZettelkastenConfig(
        base_dir=tmp_path,
        notes_dir=Path("notes"),
        database=database_url,
    )

    assert not cfg.uses_sqlite()
    assert cfg.get_db_url() == database_url
    assert not (tmp_path / "db").exists()


def test_config_resolves_relative_sqlite_url(tmp_path):
    cfg = ZettelkastenConfig(
        base_dir=tmp_path,
        notes_dir=Path("notes"),
        database="sqlite:///relative.db",
    )

    db_url = cfg.get_db_url()
    expected_path = tmp_path / "relative.db"

    assert cfg.uses_sqlite()
    assert make_url(db_url).database == str(expected_path)
    assert expected_path.parent.exists()
