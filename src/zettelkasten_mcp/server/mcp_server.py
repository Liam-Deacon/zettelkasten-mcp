"""MCP server implementation for the Zettelkasten."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, TypeAlias

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field
from smithery.decorators import smithery
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.engine.url import make_url

from zettelkasten_mcp.config import config
from zettelkasten_mcp.models.db_models import init_db
from zettelkasten_mcp.models.schema import LinkType, Note, NoteType, Tag
from zettelkasten_mcp.services.search_service import SearchService
from zettelkasten_mcp.services.zettel_service import ZettelService
from zettelkasten_mcp.utils import setup_logging

logger = logging.getLogger(__name__)


#: Transport types supported by Zettelkasten MCP server
TransportType: TypeAlias = Literal["sse", "stdio", "streamable-http"]


class ZettelkastenConfigSchema(BaseModel):
    """Configuration schema for Zettelkasten MCP server deployed on Smithery."""

    notes_dir: str = Field(
        default="data/notes",
        description="Directory where markdown note files are stored",
    )
    database: str = Field(
        default="data/db/zettelkasten.db",
        description="SQLite file path or SQLAlchemy URL for the index database. "
        "Supports PostgreSQL, MySQL, and SQL Server via SQLAlchemy URLs, "
        "e.g. postgresql+psycopg://user:password@host:port/dbname",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )


class ZettelkastenMcpServer:
    """MCP server for Zettelkasten."""

    def __init__(self) -> None:
        """Initialize the MCP server."""
        self.mcp = FastMCP(config.server_name)
        # Services
        self.zettel_service = ZettelService()
        self.search_service = SearchService(self.zettel_service)
        # Initialize services
        self.initialize()
        # Register tools
        self._register_tools()
        self._register_resources()
        self._register_prompts()

    def initialize(self) -> None:
        """Initialize services."""
        try:
            self.zettel_service.initialize()
            self.search_service.initialize()
            logger.info("Zettelkasten MCP server initialized")
        except Exception as err:
            logger.error(f"Failed to initialize services: {err}")
            raise

    def format_error_response(self, error: Exception) -> str:
        """Format an error response in a consistent way.

        Args:
            error: The exception that occurred

        Returns:
            Formatted error message with appropriate level of detail
        """
        # Generate a unique error ID for traceability in logs
        error_id = str(uuid.uuid4())[:8]

        if isinstance(error, ValueError):
            # Domain validation errors - typically safe to show to users
            logger.error(f"Validation error [{error_id}]: {str(error)}")
            return f"Error: {str(error)}"
        elif isinstance(error, (IOError, OSError)):
            # File system errors - don't expose paths or detailed error messages
            logger.error(f"File system error [{error_id}]: {str(error)}", exc_info=True)
            # return f"Unable to access the requested resource. Error ID: {error_id}"
            return f"Error: {str(error)}"
        else:
            # Unexpected errors - log with full stack trace but return generic message
            logger.error(f"Unexpected error [{error_id}]: {str(error)}", exc_info=True)
            # return f"An unexpected error occurred. Error ID: {error_id}"
            return f"Error: {str(error)}"

    def _register_tools(self) -> None:
        """Register MCP tools."""

        # Create a new note
        @self.mcp.tool(
            name="zk_create_note",
            description="Create a new atomic Zettelkasten note with a unique ID, content, and optional tags.",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
            },
        )
        def zk_create_note(
            title: str,
            content: str,
            note_type: str = "permanent",
            tags: str | None = None,
        ) -> str:
            """Create a new atomic Zettelkasten note with a unique ID, content, and optional tags.

            Args:
                title: The title of the note
                content: The main content of the note in markdown format
                note_type: Type of note - one of: fleeting, literature, permanent, structure, hub (default: permanent)
                tags: Optional comma-separated list of tags for categorization
            """
            try:
                # Convert note_type string to enum
                try:
                    note_type_enum = NoteType(note_type.lower())
                except ValueError:
                    return f"Invalid note type: {note_type}. Valid types are: {', '.join(t.value for t in NoteType)}"

                # Convert tags string to list
                tag_list = []
                if tags:
                    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

                # Create the note
                note = self.zettel_service.create_note(
                    title=title,
                    content=content,
                    note_type=note_type_enum,
                    tags=tag_list,
                )
                return f"Note created successfully with ID: {note.id}"
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_create_note registered")

        # Get a note by ID or title
        @self.mcp.tool(
            name="zk_get_note",
            description="Retrieve the full content and metadata of a note by its unique ID or title.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_get_note(identifier: str) -> str:
            """Retrieve the full content and metadata of a note by its unique ID or title.

            Args:
                identifier: The unique ID or exact title of the note to retrieve
            """
            try:
                identifier = str(identifier)
                # Try to get by ID first
                note = self.zettel_service.get_note(identifier)
                # If not found, try by title
                if not note:
                    note = self.zettel_service.get_note_by_title(identifier)
                if not note:
                    return f"Note not found: {identifier}"

                # Format the note
                result = f"# {note.title}\n"
                result += f"ID: {note.id}\n"
                result += f"Type: {note.note_type.value}\n"
                result += f"Created: {note.created_at.isoformat()}\n"
                result += f"Updated: {note.updated_at.isoformat()}\n"
                if note.tags:
                    result += f"Tags: {', '.join(tag.name for tag in note.tags)}\n"
                # Add note content, including the Links section added by _note_to_markdown()
                result += f"\n{note.content}\n"
                return result
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_get_note registered")

        # Update a note
        @self.mcp.tool(
            name="zk_update_note",
            description="Update the title, content, type, or tags of an existing note.",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_update_note(
            note_id: str,
            title: str | None = None,
            content: str | None = None,
            note_type: str | None = None,
            tags: str | None = None,
        ) -> str:
            """Update the title, content, type, or tags of an existing note.

            Args:
                note_id: The unique ID of the note to update
                title: New title for the note (optional)
                content: New markdown content for the note (optional)
                note_type: New note type - one of: fleeting, literature, permanent, structure, hub (optional)
                tags: New comma-separated list of tags, or empty string to clear tags (optional)
            """
            try:
                # Get the note
                note = self.zettel_service.get_note(str(note_id))
                if not note:
                    return f"Note not found: {note_id}"

                # Convert note_type string to enum if provided
                note_type_enum = None
                if note_type:
                    try:
                        note_type_enum = NoteType(note_type.lower())
                    except ValueError:
                        return f"Invalid note type: {note_type}. Valid types are: {', '.join(t.value for t in NoteType)}"

                # Convert tags string to list if provided
                tag_list = None
                if tags is not None:  # Allow empty string to clear tags
                    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

                # Update the note
                updated_note = self.zettel_service.update_note(
                    note_id=note_id,
                    title=title,
                    content=content,
                    note_type=note_type_enum,
                    tags=tag_list,
                )
                return f"Note updated successfully: {updated_note.id}"
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_update_note registered")

        # Delete a note
        @self.mcp.tool(
            name="zk_delete_note",
            description="Permanently delete a note and all its associated links from the Zettelkasten.",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
            },
        )
        def zk_delete_note(note_id: str) -> str:
            """Permanently delete a note and all its associated links from the Zettelkasten.

            Args:
                note_id: The unique ID of the note to permanently delete
            """
            try:
                # Check if note exists
                note = self.zettel_service.get_note(note_id)
                if not note:
                    return f"Note not found: {note_id}"

                # Delete the note
                self.zettel_service.delete_note(str(note_id))
                return f"Note deleted successfully: {note_id}"
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_delete_note registered")

        # Add a link between notes
        @self.mcp.tool(
            name="zk_create_link",
            description="Create a semantic link between two notes to build knowledge connections.",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
            },
        )
        def zk_create_link(
            source_id: str,
            target_id: str,
            link_type: str = "reference",
            description: str | None = None,
            bidirectional: bool = False,
        ) -> str:
            """Create a semantic link between two notes to build knowledge connections.

            Args:
                source_id: The unique ID of the source note
                target_id: The unique ID of the target note
                link_type: Type of semantic relationship - one of: reference, extends, refines, contradicts, questions, supports, related (default: reference)
                description: Optional text describing the nature of this specific link
                bidirectional: If true, creates links in both directions (source→target and target→source)
            """
            try:
                # Convert link_type string to enum
                try:
                    source_id_str = str(source_id)
                    target_id_str = str(target_id)
                    link_type_enum = LinkType(link_type.lower())
                except ValueError:
                    return f"Invalid link type: {link_type}. Valid types are: {', '.join(t.value for t in LinkType)}"

                # Create the link
                source_note, target_note = self.zettel_service.create_link(
                    source_id=source_id,
                    target_id=target_id,
                    link_type=link_type_enum,
                    description=description,
                    bidirectional=bidirectional,
                )
                if bidirectional:
                    return f"Bidirectional link created between {source_id} and {target_id}"
                else:
                    return f"Link created from {source_id} to {target_id}"
            except (Exception, sqlalchemy_exc.IntegrityError) as e:
                if "UNIQUE constraint failed" in str(e):
                    return f"A link of this type already exists between these notes. Try a different link type."
                return self.format_error_response(e)

        self.zk_create_link = zk_create_link

        logger.debug("Tool zk_create_link registered")

        # Remove a link between notes
        @self.mcp.tool(
            name="zk_remove_link",
            description="Remove an existing link between two notes.",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": True,
            },
        )
        def zk_remove_link(
            source_id: str, target_id: str, bidirectional: bool = False
        ) -> str:
            """Remove an existing link between two notes.

            Args:
                source_id: The unique ID of the source note
                target_id: The unique ID of the target note
                bidirectional: If true, removes links in both directions (source→target and target→source)
            """
            try:
                # Remove the link
                source_note, target_note = self.zettel_service.remove_link(
                    source_id=str(source_id),
                    target_id=str(target_id),
                    bidirectional=bidirectional,
                )
                if bidirectional:
                    return f"Bidirectional link removed between {source_id} and {target_id}"
                else:
                    return f"Link removed from {source_id} to {target_id}"
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_remove_link registered")

        # Search for notes
        @self.mcp.tool(
            name="zk_search_notes",
            description="Search for notes using text queries, tags, or note type filters.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_search_notes(
            query: str | None = None,
            tags: str | None = None,
            note_type: str | None = None,
            limit: int = 10,
        ) -> str:
            """Search for notes using text queries, tags, or note type filters.

            Args:
                query: Text to search for in note titles and content (optional)
                tags: Comma-separated list of tags to filter results (optional)
                note_type: Filter by note type - one of: fleeting, literature, permanent, structure, hub (optional)
                limit: Maximum number of results to return (default: 10)
            """
            try:
                # Convert tags string to list if provided
                tag_list = None
                if tags:
                    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

                # Convert note_type string to enum if provided
                note_type_enum = None
                if note_type:
                    try:
                        note_type_enum = NoteType(note_type.lower())
                    except ValueError:
                        return f"Invalid note type: {note_type}. Valid types are: {', '.join(t.value for t in NoteType)}"

                # Perform search
                results = self.search_service.search_combined(
                    text=query, tags=tag_list, note_type=note_type_enum
                )

                # Limit results
                results = results[:limit]
                if not results:
                    return "No matching notes found."

                # Format results
                output = f"Found {len(results)} matching notes:\n\n"
                for i, result in enumerate(results, 1):
                    note = result.note
                    output += f"{i}. {note.title} (ID: {note.id})\n"
                    if note.tags:
                        output += (
                            f"   Tags: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    output += f"   Created: {note.created_at.strftime('%Y-%m-%d')}\n"
                    # Add a snippet of content (first 150 chars)
                    content_preview = note.content[:150].replace("\n", " ")
                    if len(note.content) > 150:
                        content_preview += "..."
                    output += f"   Preview: {content_preview}\n\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_search_notes registered")

        # Get linked notes
        @self.mcp.tool(
            name="zk_get_linked_notes",
            description="Find all notes connected to a specific note through links.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_get_linked_notes(note_id: str, direction: str = "both") -> str:
            """Find all notes connected to a specific note through links.

            Args:
                note_id: The unique ID of the note to find connections for
                direction: Link direction to explore - one of: outgoing (links from this note), incoming (links to this note), both (default: both)
            """
            try:
                if direction not in ["outgoing", "incoming", "both"]:
                    return f"Invalid direction: {direction}. Use 'outgoing', 'incoming', or 'both'."
                # Get linked notes
                linked_notes = self.zettel_service.get_linked_notes(
                    str(note_id), direction
                )
                if not linked_notes:
                    return f"No {direction} links found for note {note_id}."
                # Format results
                output = f"Found {len(linked_notes)} {direction} linked notes for {note_id}:\n\n"
                for i, note in enumerate(linked_notes, 1):
                    output += f"{i}. {note.title} (ID: {note.id})\n"
                    if note.tags:
                        output += (
                            f"   Tags: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    # Try to determine link type
                    if direction in ["outgoing", "both"]:
                        # Check source note's outgoing links
                        source_note = self.zettel_service.get_note(str(note_id))
                        if source_note:
                            for link in source_note.links:
                                if str(link.target_id) == str(
                                    note.id
                                ):  # Explicit string conversion for comparison
                                    output += f"   Link type: {link.link_type.value}\n"
                                    if link.description:
                                        output += (
                                            f"   Description: {link.description}\n"
                                        )
                                    break
                    if direction in ["incoming", "both"]:
                        # Check target note's outgoing links
                        for link in note.links:
                            if str(link.target_id) == str(
                                note_id
                            ):  # Explicit string conversion for comparison
                                output += (
                                    f"   Incoming link type: {link.link_type.value}\n"
                                )
                                if link.description:
                                    output += f"   Description: {link.description}\n"
                                break
                    output += "\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        self.zk_get_linked_notes = zk_get_linked_notes

        logger.debug("Tool zk_get_linked_notes registered")

        # Get all tags
        @self.mcp.tool(
            name="zk_get_all_tags",
            description="Retrieve a complete list of all tags used across the Zettelkasten.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_get_all_tags() -> str:
            """Retrieve a complete list of all tags used across the Zettelkasten."""
            try:
                tags = self.zettel_service.get_all_tags()
                if not tags:
                    return "No tags found in the Zettelkasten."

                # Format results
                output = f"Found {len(tags)} tags:\n\n"
                # Sort alphabetically
                tags.sort(key=lambda t: t.name.lower())
                for i, tag in enumerate(tags, 1):
                    output += f"{i}. {tag.name}\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_get_all_tags registered")

        # Find similar notes
        @self.mcp.tool(
            name="zk_find_similar_notes",
            description="Discover notes with similar content using semantic similarity analysis.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_find_similar_notes(
            note_id: str, threshold: float = 0.3, limit: int = 5
        ) -> str:
            """Discover notes with similar content using semantic similarity analysis.

            Args:
                note_id: The unique ID of the reference note to compare against
                threshold: Minimum similarity score from 0.0 (unrelated) to 1.0 (identical) (default: 0.3)
                limit: Maximum number of similar notes to return (default: 5)
            """
            try:
                # Get similar notes
                similar_notes = self.zettel_service.find_similar_notes(
                    str(note_id), threshold
                )
                # Limit results
                similar_notes = similar_notes[:limit]
                if not similar_notes:
                    return f"No similar notes found for {note_id} with threshold {threshold}."

                # Format results
                output = f"Found {len(similar_notes)} similar notes for {note_id}:\n\n"
                for i, (note, similarity) in enumerate(similar_notes, 1):
                    output += f"{i}. {note.title} (ID: {note.id})\n"
                    output += f"   Similarity: {similarity:.2f}\n"
                    if note.tags:
                        output += (
                            f"   Tags: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    # Add a snippet of content (first 100 chars)
                    content_preview = note.content[:100].replace("\n", " ")
                    if len(note.content) > 100:
                        content_preview += "..."
                    output += f"   Preview: {content_preview}\n\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_find_similar_notes registered")

        # Find central notes
        @self.mcp.tool(
            name="zk_find_central_notes",
            description="Identify the most connected notes that serve as knowledge hubs.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_find_central_notes(limit: int = 10) -> str:
            """Identify the most connected notes that serve as knowledge hubs.

            Notes are ranked by their total number of connections (incoming + outgoing links),
            determining their centrality in the knowledge network. These central notes often
            represent key concepts or structure notes.

            Args:
                limit: Maximum number of central notes to return (default: 10)
            """
            try:
                # Get central notes
                central_notes = self.search_service.find_central_notes(limit)
                if not central_notes:
                    return "No notes found with connections."

                # Format results
                output = "Central notes in the Zettelkasten (most connected):\n\n"
                for i, (note, connection_count) in enumerate(central_notes, 1):
                    output += f"{i}. {note.title} (ID: {note.id})\n"
                    output += f"   Connections: {connection_count}\n"
                    if note.tags:
                        output += (
                            f"   Tags: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    # Add a snippet of content (first 100 chars)
                    content_preview = note.content[:100].replace("\n", " ")
                    if len(note.content) > 100:
                        content_preview += "..."
                    output += f"   Preview: {content_preview}\n\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_find_central_notes registered")

        # Find orphaned notes
        @self.mcp.tool(
            name="zk_find_orphaned_notes",
            description="Find isolated notes that have no links to or from other notes.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_find_orphaned_notes() -> str:
            """Find isolated notes that have no links to or from other notes.

            Orphaned notes may indicate fleeting ideas that need integration or cleanup.
            """
            try:
                # Get orphaned notes
                orphans = self.search_service.find_orphaned_notes()
                if not orphans:
                    return "No orphaned notes found."

                # Format results
                output = f"Found {len(orphans)} orphaned notes:\n\n"
                for i, note in enumerate(orphans, 1):
                    output += f"{i}. {note.title} (ID: {note.id})\n"
                    if note.tags:
                        output += (
                            f"   Tags: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    # Add a snippet of content (first 100 chars)
                    content_preview = note.content[:100].replace("\n", " ")
                    if len(note.content) > 100:
                        content_preview += "..."
                    output += f"   Preview: {content_preview}\n\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_find_orphaned_notes registered")

        # List notes by date range
        @self.mcp.tool(
            name="zk_list_notes_by_date",
            description="List notes created or modified within a specific date range.",
            annotations={
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_list_notes_by_date(
            start_date: str | None = None,
            end_date: str | None = None,
            use_updated: bool = False,
            limit: int = 10,
        ) -> str:
            """List notes created or modified within a specific date range.

            Args:
                start_date: Start of date range in ISO format YYYY-MM-DD (optional, defaults to earliest)
                end_date: End of date range in ISO format YYYY-MM-DD (optional, defaults to latest)
                use_updated: If true, filter by modification date instead of creation date (default: false)
                limit: Maximum number of results to return (default: 10)
            """
            try:
                # Parse dates
                start_datetime = None
                if start_date:
                    start_datetime = datetime.fromisoformat(f"{start_date}T00:00:00")
                end_datetime = None
                if end_date:
                    end_datetime = datetime.fromisoformat(f"{end_date}T23:59:59")

                # Get notes
                notes = self.search_service.find_notes_by_date_range(
                    start_date=start_datetime,
                    end_date=end_datetime,
                    use_updated=use_updated,
                )

                # Limit results
                notes = notes[:limit]
                if not notes:
                    date_type = "updated" if use_updated else "created"
                    date_range = ""
                    if start_date and end_date:
                        date_range = f" between {start_date} and {end_date}"
                    elif start_date:
                        date_range = f" after {start_date}"
                    elif end_date:
                        date_range = f" before {end_date}"
                    return f"No notes found {date_type}{date_range}."

                # Format results
                date_type = "updated" if use_updated else "created"
                output = f"Notes {date_type}"
                if start_date or end_date:
                    if start_date and end_date:
                        output += f" between {start_date} and {end_date}"
                    elif start_date:
                        output += f" after {start_date}"
                    elif end_date:
                        output += f" before {end_date}"
                output += f" (showing {len(notes)} results):\n\n"
                for i, note in enumerate(notes, 1):
                    date = note.updated_at if use_updated else note.created_at
                    output += f"{i}. {note.title} (ID: {note.id})\n"
                    output += f"   {date_type.capitalize()}: {date.strftime('%Y-%m-%d %H:%M')}\n"
                    if note.tags:
                        output += (
                            f"   Tags: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    # Add a snippet of content (first 100 chars)
                    content_preview = note.content[:100].replace("\n", " ")
                    if len(note.content) > 100:
                        content_preview += "..."
                    output += f"   Preview: {content_preview}\n\n"
                return output
            except ValueError as e:
                # Special handling for date parsing errors
                logger.error(f"Date parsing error: {str(e)}")
                return f"Error parsing date: {str(e)}"
            except Exception as e:
                return self.format_error_response(e)

        logger.debug("Tool zk_list_notes_by_date registered")

        # Rebuild the index
        @self.mcp.tool(
            name="zk_rebuild_index",
            description="Rebuild the database index from markdown files after manual file edits.",
            annotations={
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
            },
        )
        def zk_rebuild_index() -> str:
            """Rebuild the database index from markdown files after manual file edits.

            Use this after editing note files directly in the filesystem to sync changes
            back to the database. This is a safe operation that reconstructs the index
            from the source of truth (markdown files).
            """
            try:
                # Get count before rebuild
                note_count_before = len(self.zettel_service.get_all_notes())

                # Perform the rebuild
                self.zettel_service.rebuild_index()

                # Get count after rebuild
                note_count_after = len(self.zettel_service.get_all_notes())

                # Return a detailed success message
                return (
                    f"Database index rebuilt successfully.\n"
                    f"Notes processed: {note_count_after}\n"
                    f"Change in note count: {note_count_after - note_count_before}"
                )
            except Exception as e:
                # Provide a detailed error message
                logger.error(f"Failed to rebuild index: {e}", exc_info=True)
                return self.format_error_response(e)

        logger.debug("Tool zk_rebuild_index registered")

    def _register_resources(self) -> None:
        """Register MCP resources."""

        @self.mcp.resource(
            "zettelkasten://notes/all",
            name="All Notes",
            description="Complete list of all notes in the Zettelkasten with basic metadata",
        )
        def get_all_notes() -> str:
            """Get a list of all notes in the Zettelkasten."""
            try:
                notes = self.zettel_service.get_all_notes()
                if not notes:
                    return "No notes found in the Zettelkasten."

                output = f"# All Notes in Zettelkasten ({len(notes)} total)\n\n"
                for note in notes:
                    output += f"## {note.title}\n"
                    output += f"- **ID**: {note.id}\n"
                    output += f"- **Type**: {note.note_type.value}\n"
                    output += (
                        f"- **Created**: {note.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                    )
                    if note.tags:
                        output += (
                            f"- **Tags**: {', '.join(tag.name for tag in note.tags)}\n"
                        )
                    # Count links
                    link_count = len(note.links)
                    if link_count > 0:
                        output += f"- **Links**: {link_count} outgoing\n"
                    output += "\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

        @self.mcp.resource(
            "zettelkasten://notes/{note_id}",
            name="Note Content",
            description="Full content and metadata of a specific note",
        )
        def get_note_resource(note_id: str) -> str:
            """Get full content of a specific note."""
            try:
                note = self.zettel_service.get_note(note_id)
                if not note:
                    return f"Note not found: {note_id}"

                # Format the note with full details
                result = f"# {note.title}\n\n"
                result += f"**ID**: {note.id}  \n"
                result += f"**Type**: {note.note_type.value}  \n"
                result += f"**Created**: {note.created_at.isoformat()}  \n"
                result += f"**Updated**: {note.updated_at.isoformat()}  \n"
                if note.tags:
                    result += (
                        f"**Tags**: {', '.join(tag.name for tag in note.tags)}  \n"
                    )
                result += f"\n---\n\n{note.content}\n"

                # Add links section
                if note.links:
                    result += f"\n## Links ({len(note.links)})\n\n"
                    for link in note.links:
                        target = self.zettel_service.get_note(str(link.target_id))
                        target_title = target.title if target else "Unknown"
                        result += f"- **{link.link_type.value}** → [{target_title}](zettelkasten://notes/{link.target_id})\n"
                        if link.description:
                            result += f"  - {link.description}\n"

                return result
            except Exception as e:
                return self.format_error_response(e)

        @self.mcp.resource(
            "zettelkasten://tags",
            name="Tag Index",
            description="Complete list of all tags used in the Zettelkasten",
        )
        def get_tags_resource() -> str:
            """Get a list of all tags."""
            try:
                tags = self.zettel_service.get_all_tags()
                if not tags:
                    return "No tags found in the Zettelkasten."

                # Sort alphabetically
                tags.sort(key=lambda t: t.name.lower())

                output = f"# Tags in Zettelkasten ({len(tags)} total)\n\n"
                for tag in tags:
                    output += f"- {tag.name}\n"
                return output
            except Exception as e:
                return self.format_error_response(e)

    def _register_prompts(self) -> None:
        """Register MCP prompts."""

        @self.mcp.prompt(
            name="knowledge-creation",
            description="Guide for incorporating new information into your Zettelkasten",
        )
        def knowledge_creation_prompt() -> str:
            """Prompt for creating new Zettelkasten notes from information."""
            return """I've attached information I'd like to incorporate into my Zettelkasten. Please:

First, search for existing notes that might be related before creating anything new.

Then, identify 3-5 key atomic ideas from this information and for each one:
1. Create a note with an appropriate title, type, and tags
2. Draft content in my own words with proper attribution
3. Find and create meaningful connections to existing notes
4. Update any relevant structure notes

After processing all ideas, provide a summary of the notes created, connections established, and any follow-up questions you have."""

        @self.mcp.prompt(
            name="knowledge-exploration",
            description="Guide for exploring connections in your Zettelkasten",
        )
        def knowledge_exploration_prompt(topic: str = "") -> str:
            """Prompt for exploring knowledge in the Zettelkasten."""
            topic_text = f" about '{topic}'" if topic else ""
            return f"""I'd like to explore my Zettelkasten{topic_text}. Please help me:

1. Search for relevant notes{topic_text if topic else ""}
2. Identify the most connected notes (central nodes)
3. Find clusters of related ideas
4. Discover unexpected connections between different domains
5. Identify gaps or orphaned notes that need integration

As we explore, suggest:
- New connections that could be made
- Structure notes that could organize these ideas
- Questions that might lead to deeper insights"""

        @self.mcp.prompt(
            name="knowledge-synthesis",
            description="Guide for synthesizing insights from your Zettelkasten",
        )
        def knowledge_synthesis_prompt(theme: str = "") -> str:
            """Prompt for synthesizing knowledge from the Zettelkasten."""
            theme_text = f" around the theme '{theme}'" if theme else ""
            return f"""I want to synthesize insights from my Zettelkasten{theme_text}. Please:

1. Identify relevant notes and their connections{theme_text if theme else ""}
2. Trace the evolution of ideas through linked notes
3. Find patterns and recurring themes
4. Identify contradictions or tensions between ideas
5. Suggest how these ideas might combine into new insights

Help me create a structure note or synthesis that:
- Captures the key insights
- Shows how ideas relate and build on each other
- Identifies open questions or areas for further development
- Links back to the source notes"""

    async def list_tools(self):
        return await self.mcp.list_tools()

    def run(
        self,
        transport: TransportType = getattr(config, "transport", None)
        or "streamable-http",
    ) -> None:
        """Run the MCP server.

        Args:
            transport: Transport protocol to use ("stdio", "sse", or "streamable-http").
                      Defaults to "streamable-http" to ensure Smithery's ASGI
                      middleware (which serves `/.well-known/mcp-config`) is applied
                      when the server is started without an explicit transport.
        """
        self.mcp.run(transport=transport)


# Smithery server factory function
@smithery.server(config_schema=ZettelkastenConfigSchema)
def create_server(session_config: ZettelkastenConfigSchema | None = None) -> FastMCP:
    """Create and return a Zettelkasten MCP server instance.

    This factory function is used by Smithery for deployment.
    When deployed on Smithery, session_config contains user-specific settings.

    Args:
        session_config: Optional session-specific configuration from Smithery

    Returns:
        FastMCP: Configured Zettelkasten MCP server instance
    """
    # Apply session-specific configuration if provided
    if session_config:
        logger.info("Applying Smithery session configuration")
        config.notes_dir = Path(session_config.notes_dir)
        config.database = session_config.database

        # Set up logging based on session config
        setup_logging(session_config.log_level)
    else:
        # Use default logging when no session config provided
        setup_logging("INFO")

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
        raise

    # Create the server instance
    server_instance = ZettelkastenMcpServer()

    # Return the FastMCP server object
    return server_instance.mcp
