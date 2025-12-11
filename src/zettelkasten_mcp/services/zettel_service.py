"""Service layer for Zettelkasten operations."""

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from zettelkasten_mcp.config import config
from zettelkasten_mcp.models.schema import Link, LinkType, Note, NoteType, Tag
from zettelkasten_mcp.storage.base import Repository
from zettelkasten_mcp.storage.mongo_repository import MongoNoteRepository
from zettelkasten_mcp.storage.note_repository import NoteRepository

logger = logging.getLogger(__name__)


class ZettelService:
    """Service for managing Zettelkasten notes."""

    def __init__(self, repository: Optional[Repository[Note]] = None):
        """Initialize the service."""
        if repository:
            self.repository = repository
        elif config.use_mongodb():
            self.repository = MongoNoteRepository()
        else:
            self.repository = NoteRepository()

    def initialize(self) -> None:
        """Initialize the service and dependencies."""
        # Nothing to do here for synchronous implementation
        # The repository is initialized in its constructor
        pass

    def create_note(
        self,
        title: str,
        content: str,
        note_type: NoteType = NoteType.PERMANENT,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Note:
        """Create a new note."""
        if not title:
            raise ValueError("Title is required")
        if not content:
            raise ValueError("Content is required")

        # Create note object
        note = Note(
            title=title,
            content=content,
            note_type=note_type,
            tags=[Tag(name=tag) for tag in (tags or [])],
            metadata=metadata or {},
        )

        # Save to repository
        return self.repository.create(note)

    def get_note(self, note_id: str) -> Optional[Note]:
        """Retrieve a note by ID."""
        return self.repository.get(note_id)

    def get_note_by_title(self, title: str) -> Optional[Note]:
        """Retrieve a note by title."""
        return self.repository.get_by_title(title)

    def update_note(
        self,
        note_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        note_type: Optional[NoteType] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Note:
        """Update an existing note."""
        note = self.repository.get(note_id)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found")

        # Update fields
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        if note_type is not None:
            note.note_type = note_type
        if tags is not None:
            note.tags = [Tag(name=tag) for tag in tags]
        if metadata is not None:
            note.metadata = metadata

        note.updated_at = datetime.datetime.now()

        # Save to repository
        return self.repository.update(note)

    def delete_note(self, note_id: str) -> None:
        """Delete a note."""
        self.repository.delete(note_id)

    def get_all_notes(self) -> List[Note]:
        """Get all notes."""
        return self.repository.get_all()

    def search_notes(self, **kwargs: Any) -> List[Note]:
        """Search for notes based on criteria."""
        return self.repository.search(**kwargs)

    def get_notes_by_tag(self, tag: str) -> List[Note]:
        """Get notes by tag."""
        return self.repository.find_by_tag(tag)

    def add_tag_to_note(self, note_id: str, tag: str) -> Note:
        """Add a tag to a note."""
        note = self.repository.get(note_id)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found")
        note.add_tag(tag)
        return self.repository.update(note)

    def remove_tag_from_note(self, note_id: str, tag: str) -> Note:
        """Remove a tag from a note."""
        note = self.repository.get(note_id)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found")
        note.remove_tag(tag)
        return self.repository.update(note)

    def get_all_tags(self) -> List[Tag]:
        """Get all tags in the system."""
        return self.repository.get_all_tags()

    def create_link(
        self,
        source_id: str,
        target_id: str,
        link_type: LinkType = LinkType.REFERENCE,
        description: Optional[str] = None,
        bidirectional: bool = False,
        bidirectional_type: Optional[LinkType] = None,
    ) -> Tuple[Note, Optional[Note]]:
        """Create a link between notes with proper bidirectional semantics.

        Args:
            source_id: ID of the source note
            target_id: ID of the target note
            link_type: Type of link from source to target
            description: Optional description of the link
            bidirectional: Whether to create a link in both directions
            bidirectional_type: Optional custom link type for the reverse direction
                If not provided, an appropriate inverse relation will be used

        Returns:
            Tuple of (source_note, target_note or None)
        """
        source_note = self.repository.get(source_id)
        if not source_note:
            raise ValueError(f"Source note with ID {source_id} not found")
        target_note = self.repository.get(target_id)
        if not target_note:
            raise ValueError(f"Target note with ID {target_id} not found")

        # Check if this link already exists before attempting to add it
        for link in source_note.links:
            if link.target_id == target_id and link.link_type == link_type:
                # Link already exists, no need to add it again
                if not bidirectional:
                    return source_note, None
                break
        else:
            # Only add the link if it doesn't exist
            source_note.add_link(target_id, link_type, description)
            source_note = self.repository.update(source_note)

        # If bidirectional, add link from target to source with appropriate semantics
        reverse_note = None
        if bidirectional:
            # If no explicit bidirectional type is provided, determine appropriate inverse
            if bidirectional_type is None:
                # Map link types to their semantic inverses
                inverse_map = {
                    LinkType.REFERENCE: LinkType.REFERENCE,
                    LinkType.EXTENDS: LinkType.EXTENDED_BY,
                    LinkType.EXTENDED_BY: LinkType.EXTENDS,
                    LinkType.REFINES: LinkType.REFINED_BY,
                    LinkType.REFINED_BY: LinkType.REFINES,
                    LinkType.CONTRADICTS: LinkType.CONTRADICTED_BY,
                    LinkType.CONTRADICTED_BY: LinkType.CONTRADICTS,
                    LinkType.QUESTIONS: LinkType.QUESTIONED_BY,
                    LinkType.QUESTIONED_BY: LinkType.QUESTIONS,
                    LinkType.SUPPORTS: LinkType.SUPPORTED_BY,
                    LinkType.SUPPORTED_BY: LinkType.SUPPORTS,
                    LinkType.RELATED: LinkType.RELATED,
                }
                bidirectional_type = inverse_map.get(link_type, link_type)

            # Check if the reverse link already exists before adding it
            for link in target_note.links:
                if link.target_id == source_id and link.link_type == bidirectional_type:
                    # Reverse link already exists, no need to add it again
                    return source_note, target_note

            # Only add the reverse link if it doesn't exist
            target_note.add_link(source_id, bidirectional_type, description)
            reverse_note = self.repository.update(target_note)

        return source_note, reverse_note

    def remove_link(
        self,
        source_id: str,
        target_id: str,
        link_type: Optional[LinkType] = None,
        bidirectional: bool = False,
    ) -> Tuple[Note, Optional[Note]]:
        """Remove a link between notes."""
        source_note = self.repository.get(source_id)
        if not source_note:
            raise ValueError(f"Source note with ID {source_id} not found")

        # Remove link from source to target
        source_note.remove_link(target_id, link_type)
        source_note = self.repository.update(source_note)

        # If bidirectional, remove link from target to source
        reverse_note = None
        if bidirectional:
            target_note = self.repository.get(target_id)
            if target_note:
                target_note.remove_link(source_id, link_type)
                reverse_note = self.repository.update(target_note)

        return source_note, reverse_note

    def get_linked_notes(self, note_id: str, direction: str = "outgoing") -> List[Note]:
        """Get notes linked to/from a note."""
        note = self.repository.get(note_id)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found")
        return self.repository.find_linked_notes(note_id, direction)

    def rebuild_index(self) -> None:
        """Rebuild the database index from files."""
        self.repository.rebuild_index()

    def export_note(self, note_id: str, format: str = "markdown") -> str:
        """Export a note in the specified format."""
        note = self.repository.get(note_id)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found")

        if format.lower() == "markdown":
            return note.to_markdown()
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def find_similar_notes(
        self, note_id: str, threshold: float = 0.5
    ) -> List[Tuple[Note, float]]:
        """Find notes similar to the given note based on shared tags and links."""
        note = self.repository.get(note_id)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found")

        # Get all notes
        all_notes = self.repository.get_all()
        results = []

        # Set of this note's tags and links
        note_tags = {tag.name for tag in note.tags}
        note_links = {link.target_id for link in note.links}

        # Add notes linked to this note
        incoming_notes = self.repository.find_linked_notes(note_id, "incoming")
        note_incoming = {n.id for n in incoming_notes}

        # For each note, calculate similarity
        for other_note in all_notes:
            if other_note.id == note_id:
                continue

            # Calculate tag overlap
            other_tags = {tag.name for tag in other_note.tags}
            tag_overlap = len(note_tags.intersection(other_tags))

            # Calculate link overlap (outgoing)
            other_links = {link.target_id for link in other_note.links}
            link_overlap = len(note_links.intersection(other_links))

            # Check if other note links to this note
            incoming_overlap = 1 if other_note.id in note_incoming else 0

            # Check if this note links to other note
            outgoing_overlap = 1 if other_note.id in note_links else 0

            # Calculate similarity score
            # Weight: 40% tags, 20% outgoing links, 20% incoming links, 20% direct connections
            total_possible = (
                max(len(note_tags), len(other_tags)) * 0.4
                + max(len(note_links), len(other_links)) * 0.2
                + 1 * 0.2  # Possible incoming link
                + 1 * 0.2  # Possible outgoing link
            )

            # Avoid division by zero
            if total_possible == 0:
                similarity = 0.0
            else:
                similarity = (
                    (tag_overlap * 0.4)
                    + (link_overlap * 0.2)
                    + (incoming_overlap * 0.2)
                    + (outgoing_overlap * 0.2)
                ) / total_possible

            if similarity >= threshold:
                results.append((other_note, similarity))

        # Sort by similarity (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        return results
