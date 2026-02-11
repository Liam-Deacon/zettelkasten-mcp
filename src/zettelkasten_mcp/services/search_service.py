"""Service for searching and discovering notes in the Zettelkasten."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import joinedload

from zettelkasten_mcp.models.db_models import DBLink, DBNote
from zettelkasten_mcp.models.schema import LinkType, Note, NoteType, Tag
from zettelkasten_mcp.services.zettel_service import ZettelService


@dataclass
class SearchResult:
    """A search result with a note and its relevance score."""

    note: Note
    score: float
    matched_terms: Set[str]
    matched_context: str


class SearchService:
    """Service for searching notes in the Zettelkasten."""

    def __init__(self, zettel_service: Optional[ZettelService] = None):
        """Initialize the search service."""
        self.zettel_service = zettel_service or ZettelService()

    def initialize(self) -> None:
        """Initialize the service and dependencies."""
        # Initialize the zettel service if it hasn't been initialized
        self.zettel_service.initialize()

    def search_by_text(
        self, query: str, include_content: bool = True, include_title: bool = True
    ) -> List[SearchResult]:
        """Search for notes by text content."""
        if not query:
            return []

        # Normalize query
        query = query.lower()
        query_terms = set(query.split())

        # Get all notes
        all_notes = self.zettel_service.get_all_notes()
        results = []

        for note in all_notes:
            score = 0.0
            matched_terms: Set[str] = set()
            matched_context = ""

            # Check title
            if include_title and note.title:
                title_lower = note.title.lower()
                # Exact match in title is highest score
                if query in title_lower:
                    score += 2.0
                    matched_context = f"Title: {note.title}"
                # Check for term matches in title
                for term in query_terms:
                    if term in title_lower:
                        score += 0.5
                        matched_terms.add(term)

            # Check content
            if include_content and note.content:
                content_lower = note.content.lower()
                # Exact match in content
                if query in content_lower:
                    score += 1.0
                    # Extract a snippet around the match
                    index = content_lower.find(query)
                    start = max(0, index - 40)
                    end = min(len(content_lower), index + len(query) + 40)
                    snippet = note.content[start:end]
                    matched_context = f"Content: ...{snippet}..."
                # Check for term matches in content
                for term in query_terms:
                    if term in content_lower:
                        score += 0.2
                        matched_terms.add(term)

            # Add to results if score is positive
            if score > 0:
                results.append(
                    SearchResult(
                        note=note,
                        score=score,
                        matched_terms=matched_terms,
                        matched_context=matched_context,
                    )
                )

        # Sort by score (descending)
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def search_by_tag(self, tags: Union[str, List[str]]) -> List[Note]:
        """Search for notes by tags."""
        if isinstance(tags, str):
            return self.zettel_service.get_notes_by_tag(tags)
        else:
            # If we have multiple tags, find notes with any of the tags
            all_matching_notes = []
            for tag in tags:
                notes = self.zettel_service.get_notes_by_tag(tag)
                all_matching_notes.extend(notes)
            # Remove duplicates by converting to a dictionary by ID
            unique_notes = {note.id: note for note in all_matching_notes}
            return list(unique_notes.values())

    def search_by_link(self, note_id: str, direction: str = "both") -> List[Note]:
        """Search for notes linked to/from a note."""
        return self.zettel_service.get_linked_notes(note_id, direction)

    def find_orphaned_notes(self) -> List[Note]:
        """Find notes with no incoming or outgoing links."""
        orphans = []

        with self.zettel_service.repository.session_factory() as session:
            # Subquery for notes with links
            notes_with_links = (
                select(DBNote.id)
                .outerjoin(
                    DBLink,
                    or_(DBNote.id == DBLink.source_id, DBNote.id == DBLink.target_id),
                )
                .where(or_(DBLink.source_id != None, DBLink.target_id != None))
                .subquery()
            )

            # Query for notes without links
            query = (
                select(DBNote)
                .options(
                    joinedload(DBNote.tags),
                    joinedload(DBNote.outgoing_links),
                    joinedload(DBNote.incoming_links),
                )
                .where(DBNote.id.not_in(select(notes_with_links)))
            )

            result = session.execute(query)
            orphaned_db_notes = result.unique().scalars().all()

            # Convert DB notes to model Notes
            for db_note in orphaned_db_notes:
                note = self.zettel_service.get_note(db_note.id)
                if note:
                    orphans.append(note)

        return orphans

    def find_central_notes(self, limit: int = 10) -> List[Tuple[Note, int]]:
        """Find notes with the most connections (incoming + outgoing links)."""
        note_connections = []
        # Direct database query to count connections for all notes at once
        with self.zettel_service.repository.session_factory() as session:
            # Use a CTE for better readability and performance
            query = text(
                """
            WITH outgoing AS (
                SELECT source_id as note_id, COUNT(*) as outgoing_count 
                FROM links 
                GROUP BY source_id
            ),
            incoming AS (
                SELECT target_id as note_id, COUNT(*) as incoming_count 
                FROM links 
                GROUP BY target_id
            )
            SELECT n.id,
                COALESCE(o.outgoing_count, 0) as outgoing,
                COALESCE(i.incoming_count, 0) as incoming,
                (COALESCE(o.outgoing_count, 0) + COALESCE(i.incoming_count, 0)) as total
            FROM notes n
            LEFT JOIN outgoing o ON n.id = o.note_id
            LEFT JOIN incoming i ON n.id = i.note_id
            WHERE (COALESCE(o.outgoing_count, 0) + COALESCE(i.incoming_count, 0)) > 0
            ORDER BY total DESC
            LIMIT :limit
            """
            )

            results = session.execute(query, {"limit": limit}).all()

            # Process results
            for note_id, outgoing_count, incoming_count, total_connections in results:
                total_connections = outgoing_count + incoming_count
                if total_connections > 0:  # Only include notes with connections
                    note = self.zettel_service.get_note(note_id)
                    if note:
                        note_connections.append((note, total_connections))

        # Sort by total connections (descending)
        note_connections.sort(key=lambda x: x[1], reverse=True)

        # Return top N notes
        return note_connections[:limit]

    def find_notes_by_date_range(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_updated: bool = False,
    ) -> List[Note]:
        """Find notes created or updated within a date range."""
        all_notes = self.zettel_service.get_all_notes()
        matching_notes = []

        for note in all_notes:
            # Get the relevant date
            date = note.updated_at if use_updated else note.created_at

            # Check if in range
            if start_date and date < start_date:
                continue
            if end_date and date >= end_date + datetime.timedelta(seconds=1):
                continue

            matching_notes.append(note)

        # Sort by date (descending)
        matching_notes.sort(
            key=lambda x: x.updated_at if use_updated else x.created_at, reverse=True
        )

        return matching_notes

    def find_similar_notes(self, note_id: str) -> List[Tuple[Note, float]]:
        """Find notes similar to the given note based on shared tags and links."""
        return self.zettel_service.find_similar_notes(note_id)

    def search_combined(
        self,
        text: Optional[str] = None,
        tags: Optional[List[str]] = None,
        note_type: Optional[NoteType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[SearchResult]:
        """Perform a combined search with multiple criteria."""
        # Start with all notes
        all_notes = self.zettel_service.get_all_notes()

        # Filter by criteria
        filtered_notes = []
        for note in all_notes:
            # Check note type
            if note_type and note.note_type != note_type:
                continue

            # Check date range
            if start_date and note.created_at < start_date:
                continue
            if end_date and note.created_at > end_date:
                continue

            # Check tags
            if tags:
                note_tag_names = {tag.name for tag in note.tags}
                if not any(tag in note_tag_names for tag in tags):
                    continue

            # Made it through all filters
            filtered_notes.append(note)

        # If we have a text query, score the notes
        results = []
        if text:
            text = text.lower()
            query_terms = set(text.split())

            for note in filtered_notes:
                score = 0.0
                matched_terms: Set[str] = set()
                matched_context = ""

                # Check title
                title_lower = note.title.lower()
                if text in title_lower:
                    score += 2.0
                    matched_context = f"Title: {note.title}"

                for term in query_terms:
                    if term in title_lower:
                        score += 0.5
                        matched_terms.add(term)

                # Check content
                content_lower = note.content.lower()
                if text in content_lower:
                    score += 1.0
                    index = content_lower.find(text)
                    start = max(0, index - 40)
                    end = min(len(content_lower), index + len(text) + 40)
                    snippet = note.content[start:end]
                    matched_context = f"Content: ...{snippet}..."

                for term in query_terms:
                    if term in content_lower:
                        score += 0.2
                        matched_terms.add(term)

                # Add to results if score is positive
                if score > 0:
                    results.append(
                        SearchResult(
                            note=note,
                            score=score,
                            matched_terms=matched_terms,
                            matched_context=matched_context,
                        )
                    )
        else:
            # If no text query, just add all filtered notes with a default score
            results = [
                SearchResult(
                    note=note, score=1.0, matched_terms=set(), matched_context=""
                )
                for note in filtered_notes
            ]

        # Sort by score (descending)
        results.sort(key=lambda x: x.score, reverse=True)
        return results
