"""Utility functions for the Zettelkasten MCP server."""

import logging
import sys
from datetime import datetime
from typing import Optional


def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """Set up logging configuration.
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to a log file
    """
    # Convert string level to logging level
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Base configuration
    log_config = {
        "level": numeric_level,
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }

    # Add file handler if log file is specified
    if log_file:
        log_config["filename"] = log_file
        log_config["filemode"] = "a"
    else:
        # Otherwise, log to stderr
        log_config["stream"] = sys.stderr

    # Apply configuration
    logging.basicConfig(**log_config)


def generate_timestamp_id() -> str:
    """Generate a timestamp-based ID in ISO 8601 Zettelkasten format with nanosecond precision.

    Returns:
        A string in format "YYYYMMDDTHHMMSSsssssssss" where:
        - YYYYMMDD is the date
        - T is the ISO 8601 date/time separator
        - HHMMSS is the time (hours, minutes, seconds)
        - sssssssss is the 9-digit nanosecond component
    """
    # Get nanoseconds since epoch
    ns_timestamp = time.time_ns()

    # Convert to seconds and nanosecond fraction
    seconds = ns_timestamp // 1_000_000_000
    nanoseconds = ns_timestamp % 1_000_000_000

    # Convert seconds to datetime
    timestamp = datetime.fromtimestamp(seconds)

    # Format as ISO 8601 basic format (YYYYMMDDThhmmss) with nanoseconds
    date_time = timestamp.strftime("%Y%m%dT%H%M%S")

    # Return the ISO 8601 timestamp with nanosecond precision
    return f"{date_time}{nanoseconds:09d}"


def parse_tags(tags_str: str) -> list[str]:
    """Parse a comma-separated list of tags into a list of tag strings.
    Args:
        tags_str: Comma-separated string of tags
    Returns:
        List of tag strings
    """
    if not tags_str:
        return []
    return [tag.strip() for tag in tags_str.split(",") if tag.strip()]


def format_note_for_display(
    title: str,
    id: str,
    content: str,
    tags: list[str],
    created_at: datetime,
    updated_at: datetime,
    links: Optional[list] = None,
) -> str:
    """Format a note for display in the console.
    Args:
        title: Note title
        id: Note ID
        content: Note content
        tags: List of tags
        created_at: Creation timestamp
        updated_at: Update timestamp
        links: Optional list of links
    Returns:
        Formatted string representation of the note
    """
    result = f"# {title}\n"
    result += f"ID: {id}\n"
    result += f"Created: {created_at.isoformat()}\n"
    result += f"Updated: {updated_at.isoformat()}\n"

    if tags:
        result += f"Tags: {', '.join(tags)}\n"

    result += f"\n{content}\n"

    if links:
        result += "\n## Links\n"
        for link in links:
            if hasattr(link, "description") and link.description:
                result += (
                    f"- {link.link_type.value}: {link.target_id} - {link.description}\n"
                )
            else:
                result += f"- {link.link_type.value}: {link.target_id}\n"

    return result
