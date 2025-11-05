#!/usr/bin/env python
"""Main entry point for the Zettelkasten MCP server."""
import argparse
import logging
import os
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

from zettelkasten_mcp.config import config
from zettelkasten_mcp.models.db_models import init_db
from zettelkasten_mcp.server.mcp_server import ZettelkastenMcpServer
from zettelkasten_mcp.utils import setup_logging


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Zettelkasten MCP Server")
    parser.add_argument(
        "--notes-dir",
        help="Directory for storing note files",
        type=str,
        default=os.environ.get("ZETTELKASTEN_NOTES_DIR"),
    )
    parser.add_argument(
        "--database",
        dest="database",
        help="SQLite file path or SQLAlchemy URL for the index database",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--database-path",
        dest="database",
        help=argparse.SUPPRESS,
        type=str,
        default=None,
    )
    parser.add_argument(
        "--database-url",
        dest="database",
        help=argparse.SUPPRESS,
        type=str,
        default=None,
    )
    parser.add_argument(
        "--log-level",
        help="Logging level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=os.environ.get("ZETTELKASTEN_LOG_LEVEL", "INFO"),
    )
    return parser.parse_args()


def update_config(args):
    """Update the global config with command line arguments."""
    if args.notes_dir:
        config.notes_dir = Path(args.notes_dir)
    database_value = getattr(args, "database", None)
    if database_value:
        config.database = database_value


def main():
    """Run the Zettelkasten MCP server."""
    # Parse arguments and update config
    args = parse_args()
    update_config(args)

    # Set up logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    # Ensure directories exist
    notes_dir = config.get_absolute_path(config.notes_dir)
    notes_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database schema
    try:
        db_url = config.get_db_url()
        if config.uses_sqlite():
            logger.info(f"Using SQLite database: {db_url}")
        else:
            safe_url = make_url(db_url).render_as_string(hide_password=True)
            logger.info(f"Using database URL: {safe_url}")
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)

    # Create and run the MCP server
    try:
        logger.info("Starting Zettelkasten MCP server")
        server = ZettelkastenMcpServer()
        server.run()
    except Exception as e:
        logger.error(f"Error running server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
