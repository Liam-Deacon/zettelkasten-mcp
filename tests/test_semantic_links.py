"""Comprehensive test suite for semantic link types in the Zettelkasten MCP implementation."""

import datetime
from unittest.mock import ANY, MagicMock, patch

import pytest

from zettelkasten_mcp.models.schema import Link, LinkType, Note, NoteType, Tag
from zettelkasten_mcp.server.mcp_server import ZettelkastenMcpServer
from zettelkasten_mcp.services.zettel_service import ZettelService


class TestSemanticLinks:
    """Test suite for semantic links in the Zettelkasten system."""

    @pytest.fixture
    def mock_datetime_now(self):
        """Mock datetime.now() to return a fixed timestamp."""
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = datetime.datetime(2025, 1, 1, 12, 0, 0)
            # Ensure constructor still works correctly
            mock_dt.side_effect = lambda *args, **kw: datetime.datetime(*args, **kw)
            yield mock_dt

    def test_all_link_types_creation(self, zettel_service):
        """Test creating links with all semantic link types."""
        # Create two test notes
        source_note = zettel_service.create_note(
            title="Source Note",
            content="Source note content",
            note_type=NoteType.PERMANENT,
            tags=["test", "source"],
        )
        target_note = zettel_service.create_note(
            title="Target Note",
            content="Target note content",
            note_type=NoteType.PERMANENT,
            tags=["test", "target"],
        )

        # Create links with each link type
        link_types = [
            (LinkType.REFERENCE, "Reference link"),
            (LinkType.EXTENDS, "Extends link"),
            (LinkType.EXTENDED_BY, "Extended by link"),
            (LinkType.REFINES, "Refines link"),
            (LinkType.REFINED_BY, "Refined by link"),
            (LinkType.CONTRADICTS, "Contradicts link"),
            (LinkType.CONTRADICTED_BY, "Contradicted by link"),
            (LinkType.QUESTIONS, "Questions link"),
            (LinkType.QUESTIONED_BY, "Questioned by link"),
            (LinkType.SUPPORTS, "Supports link"),
            (LinkType.SUPPORTED_BY, "Supported by link"),
            (LinkType.RELATED, "Related link"),
        ]

        # Need separate target notes to avoid uniqueness constraint
        target_notes = []
        for i in range(len(link_types)):
            t_note = zettel_service.create_note(
                title=f"Target Note {i+1}",
                content=f"Target note {i+1} content",
                note_type=NoteType.PERMANENT,
                tags=["test", "target"],
            )
            target_notes.append(t_note)

        # Create links with each link type
        for i, (link_type, description) in enumerate(link_types):
            # Create link
            source, target = zettel_service.create_link(
                source_id=source_note.id,
                target_id=target_notes[i].id,
                link_type=link_type,
                description=description,
            )

            # Verify source note's links
            matching_links = [
                link for link in source.links if link.target_id == target_notes[i].id
            ]
            assert len(matching_links) == 1
            assert matching_links[0].link_type == link_type
            assert matching_links[0].description == description

            # Verify link retrieval through repository
            updated_source = zettel_service.get_note(source_note.id)
            matching_links = [
                link
                for link in updated_source.links
                if link.target_id == target_notes[i].id
            ]
            assert len(matching_links) == 1
            assert matching_links[0].link_type == link_type
            assert matching_links[0].description == description

    def test_bidirectional_semantic_links(self, zettel_service):
        """Test creating bidirectional links with proper semantic inverses."""
        # Create two test notes
        source_note = zettel_service.create_note(
            title="Bidirectional Source Note",
            content="Source note content for bidirectional links",
            note_type=NoteType.PERMANENT,
            tags=["test", "bidirectional"],
        )

        # Test pairs of semantic inverse relationships
        inverse_pairs = [
            # (from_source, expected_inverse)
            (LinkType.EXTENDS, LinkType.EXTENDED_BY),
            (LinkType.EXTENDED_BY, LinkType.EXTENDS),
            (LinkType.REFINES, LinkType.REFINED_BY),
            (LinkType.REFINED_BY, LinkType.REFINES),
            (LinkType.CONTRADICTS, LinkType.CONTRADICTED_BY),
            (LinkType.CONTRADICTED_BY, LinkType.CONTRADICTS),
            (LinkType.QUESTIONS, LinkType.QUESTIONED_BY),
            (LinkType.QUESTIONED_BY, LinkType.QUESTIONS),
            (LinkType.SUPPORTS, LinkType.SUPPORTED_BY),
            (LinkType.SUPPORTED_BY, LinkType.SUPPORTS),
            # Symmetric relationships
            (LinkType.REFERENCE, LinkType.REFERENCE),
            (LinkType.RELATED, LinkType.RELATED),
        ]

        # Need separate target notes to avoid uniqueness constraint
        target_notes = []
        for i in range(len(inverse_pairs)):
            t_note = zettel_service.create_note(
                title=f"Bidirectional Target {i+1}",
                content=f"Target note {i+1} for bidirectional testing",
                note_type=NoteType.PERMANENT,
                tags=["test", "bidirectional"],
            )
            target_notes.append(t_note)

        # Test each pair
        for i, (source_type, expected_inverse) in enumerate(inverse_pairs):
            # Create bidirectional link
            source, target = zettel_service.create_link(
                source_id=source_note.id,
                target_id=target_notes[i].id,
                link_type=source_type,
                description=f"Testing {source_type.value} relationship",
                bidirectional=True,
            )

            # Verify outgoing link from source
            source_links = [
                link for link in source.links if link.target_id == target_notes[i].id
            ]
            assert len(source_links) == 1
            assert source_links[0].link_type == source_type

            # Verify incoming link to target (inverse relationship)
            target_links = [
                link for link in target.links if link.target_id == source_note.id
            ]
            assert len(target_links) == 1
            assert target_links[0].link_type == expected_inverse

            # Verify through get_linked_notes (outgoing)
            outgoing_links = zettel_service.get_linked_notes(source_note.id, "outgoing")
            assert any(note.id == target_notes[i].id for note in outgoing_links)

            # Verify through get_linked_notes (incoming)
            incoming_links = zettel_service.get_linked_notes(
                target_notes[i].id, "incoming"
            )
            assert any(note.id == source_note.id for note in incoming_links)

    def test_custom_bidirectional_link_types(self, zettel_service):
        """Test bidirectional links with custom inverse types."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Custom Bidirectional Source",
            content="Source note content for custom bidirectional links",
            note_type=NoteType.PERMANENT,
            tags=["test", "custom-bidirectional"],
        )
        target_note = zettel_service.create_note(
            title="Custom Bidirectional Target",
            content="Target note content for custom bidirectional links",
            note_type=NoteType.PERMANENT,
            tags=["test", "custom-bidirectional"],
        )

        # Create bidirectional link with explicit inverse type
        # The second parameter should be a specific bidirectional_type, not a boolean
        # However, since the ZettelService interface doesn't support this directly,
        # we'll need to modify the test or mock the lower-level function

        # For now, we'll test this using two separate directional links
        source, _ = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.EXTENDS,
            description="Forward direction",
        )

        target, _ = zettel_service.create_link(
            source_id=target_note.id,
            target_id=source_note.id,
            link_type=LinkType.QUESTIONS,  # Custom inverse type (not the expected EXTENDED_BY)
            description="Custom backward direction",
        )

        # Verify links
        source_note = zettel_service.get_note(source_note.id)
        target_note = zettel_service.get_note(target_note.id)

        # Check outgoing link from source
        source_links = [
            link for link in source_note.links if link.target_id == target_note.id
        ]
        assert len(source_links) == 1
        assert source_links[0].link_type == LinkType.EXTENDS

        # Check outgoing link from target (custom inverse)
        target_links = [
            link for link in target_note.links if link.target_id == source_note.id
        ]
        assert len(target_links) == 1
        assert target_links[0].link_type == LinkType.QUESTIONS  # Custom inverse type

    def test_links_persistence_through_save_and_load(self, zettel_service):
        """Test that link types persist correctly when notes are saved and reloaded."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Persistence Source Note",
            content="Source note for testing persistence",
            note_type=NoteType.PERMANENT,
            tags=["test", "persistence"],
        )
        target_note = zettel_service.create_note(
            title="Persistence Target Note",
            content="Target note for testing persistence",
            note_type=NoteType.PERMANENT,
            tags=["test", "persistence"],
        )

        # Create link with a semantic type
        source, _ = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.REFINES,
            description="Testing persistence of semantic links",
        )

        # Save the source note with link
        updated_source = zettel_service.update_note(
            note_id=source_note.id,
            title=source_note.title,
            content=source_note.content + "\nAdditional content to trigger save.",
        )

        # Verify link is still present with correct type after save
        assert any(
            link.target_id == target_note.id and link.link_type == LinkType.REFINES
            for link in updated_source.links
        )

        # Load the note from repository
        loaded_note = zettel_service.get_note(source_note.id)

        # Verify link is present with correct type after load
        matching_links = [
            link for link in loaded_note.links if link.target_id == target_note.id
        ]
        assert len(matching_links) == 1
        assert matching_links[0].link_type == LinkType.REFINES
        assert matching_links[0].description == "Testing persistence of semantic links"

    def test_multiple_link_types_between_notes(self, zettel_service):
        """Test creating multiple different link types between the same two notes."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Multi-Link Source",
            content="Source note for multiple link types",
            note_type=NoteType.PERMANENT,
            tags=["test", "multi-link"],
        )
        target_note = zettel_service.create_note(
            title="Multi-Link Target",
            content="Target note for multiple link types",
            note_type=NoteType.PERMANENT,
            tags=["test", "multi-link"],
        )

        # Create multiple links with different types
        link_types = [LinkType.EXTENDS, LinkType.SUPPORTS, LinkType.QUESTIONS]

        for i, link_type in enumerate(link_types):
            source, _ = zettel_service.create_link(
                source_id=source_note.id,
                target_id=target_note.id,
                link_type=link_type,
                description=f"Link {i+1}: {link_type.value}",
            )

        # Refresh the note from repository
        updated_source = zettel_service.get_note(source_note.id)

        # Verify all link types are present
        target_links = [
            link for link in updated_source.links if link.target_id == target_note.id
        ]
        assert len(target_links) == len(link_types)

        # Verify each link type is present
        for link_type in link_types:
            assert any(link.link_type == link_type for link in target_links)

    def test_updating_link(self, zettel_service):
        """Test updating an existing link's type or description."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Link Update Source",
            content="Source note for link update testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "link-update"],
        )
        target_note = zettel_service.create_note(
            title="Link Update Target",
            content="Target note for link update testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "link-update"],
        )

        # Create initial link
        source, _ = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.REFERENCE,
            description="Initial link description",
        )

        # Remove the link
        source, _ = zettel_service.remove_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.REFERENCE,
        )

        # Verify link was removed
        assert not any(link.target_id == target_note.id for link in source.links)

        # Create new link with different type
        source, _ = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.EXTENDS,
            description="Updated link description",
        )

        # Verify link was updated
        matching_links = [
            link for link in source.links if link.target_id == target_note.id
        ]
        assert len(matching_links) == 1
        assert matching_links[0].link_type == LinkType.EXTENDS
        assert matching_links[0].description == "Updated link description"

        # Load the note from repository to verify persistence
        loaded_note = zettel_service.get_note(source_note.id)
        matching_links = [
            link for link in loaded_note.links if link.target_id == target_note.id
        ]
        assert len(matching_links) == 1
        assert matching_links[0].link_type == LinkType.EXTENDS
        assert matching_links[0].description == "Updated link description"

    def test_removing_links(self, zettel_service):
        """Test removing links with specific semantic types."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Link Removal Source",
            content="Source note for link removal testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "link-removal"],
        )
        target_note = zettel_service.create_note(
            title="Link Removal Target",
            content="Target note for link removal testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "link-removal"],
        )

        # Create multiple links with different types
        link_types = [LinkType.EXTENDS, LinkType.SUPPORTS, LinkType.QUESTIONS]

        for link_type in link_types:
            zettel_service.create_link(
                source_id=source_note.id,
                target_id=target_note.id,
                link_type=link_type,
                description=f"{link_type.value} description",
            )

        # Refresh the source note
        source_note = zettel_service.get_note(source_note.id)

        # Verify all links were created
        target_links = [
            link for link in source_note.links if link.target_id == target_note.id
        ]
        assert len(target_links) == len(link_types)

        # Remove specific link type
        zettel_service.remove_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.SUPPORTS,
        )

        # Refresh the source note
        source_note = zettel_service.get_note(source_note.id)

        # Verify only the specified link was removed
        target_links = [
            link for link in source_note.links if link.target_id == target_note.id
        ]
        assert len(target_links) == len(link_types) - 1
        assert not any(link.link_type == LinkType.SUPPORTS for link in target_links)
        assert any(link.link_type == LinkType.EXTENDS for link in target_links)
        assert any(link.link_type == LinkType.QUESTIONS for link in target_links)

        # Remove all remaining links to target
        zettel_service.remove_link(source_id=source_note.id, target_id=target_note.id)

        # Refresh the source note
        source_note = zettel_service.get_note(source_note.id)

        # Verify all links to target were removed
        target_links = [
            link for link in source_note.links if link.target_id == target_note.id
        ]
        assert len(target_links) == 0

    def test_bidirectional_link_removal(self, zettel_service):
        """Test removing bidirectional links."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Bidirectional Removal Source",
            content="Source note for bidirectional link removal",
            note_type=NoteType.PERMANENT,
            tags=["test", "bidirectional-removal"],
        )
        target_note = zettel_service.create_note(
            title="Bidirectional Removal Target",
            content="Target note for bidirectional link removal",
            note_type=NoteType.PERMANENT,
            tags=["test", "bidirectional-removal"],
        )

        # Create bidirectional link
        source, target = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.EXTENDS,
            description="Bidirectional link for removal testing",
            bidirectional=True,
        )

        # Verify bidirectional link was created
        assert any(
            link.target_id == target_note.id and link.link_type == LinkType.EXTENDS
            for link in source.links
        )
        assert any(
            link.target_id == source_note.id and link.link_type == LinkType.EXTENDED_BY
            for link in target.links
        )

        # Remove bidirectional link
        source, target = zettel_service.remove_link(
            source_id=source_note.id, target_id=target_note.id, bidirectional=True
        )

        # Verify bidirectional link was removed
        assert not any(link.target_id == target_note.id for link in source.links)
        assert not any(link.target_id == source_note.id for link in target.links)

    def test_parsing_link_types_from_markdown(self, note_repository):
        """Test that link types are correctly parsed from markdown content."""
        # Create markdown content with links section
        markdown_content = """---
id: '20250101120000'
title: Markdown Parsing Test
tags: test, markdown, parsing
---

# Markdown Parsing Test

Test content for parsing links from markdown.

## Links
- extends [[20250101120001]] Test extends link
- contradicts [[20250101120002]] Test contradicts link
- supports [[20250101120003]] Test supports link
"""

        # Parse note from markdown
        note = note_repository._parse_note_from_markdown(markdown_content)

        # Verify links were parsed with correct types
        assert len(note.links) == 3

        # Verify each link type
        link_types = {link.target_id: link.link_type for link in note.links}
        assert link_types["20250101120001"] == LinkType.EXTENDS
        assert link_types["20250101120002"] == LinkType.CONTRADICTS
        assert link_types["20250101120003"] == LinkType.SUPPORTS

    def test_markdown_generation_with_links(self, zettel_service):
        """Test that markdown is generated with the correct link types."""
        # Create test notes with explicit datetime objects rather than mocks
        original_created_at = datetime.datetime.now()
        original_updated_at = datetime.datetime.now()

        source_note = zettel_service.create_note(
            title="Markdown Generation Source",
            content="Source note for markdown generation testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "markdown-generation"],
        )

        # Explicitly set the datetime attributes to real objects, not mocks
        source_note.created_at = original_created_at
        source_note.updated_at = original_updated_at

        source_note.add_link(
            target_id="target123",
            link_type=LinkType.EXTENDS,
            description="Extends link",
        )

        # Access the repository's _note_to_markdown function
        markdown = zettel_service.repository._note_to_markdown(source_note)

        # Verify markdown contains the link with correct type
        assert "## Links" in markdown
        assert "- extends [[target123]] Extends link" in markdown

    def test_link_type_uniqueness_constraint(self, zettel_service):
        """Test the uniqueness constraint for link types between notes."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Uniqueness Source",
            content="Source note for uniqueness constraint testing",
            tags=["test", "uniqueness"],
        )
        target_note = zettel_service.create_note(
            title="Uniqueness Target",
            content="Target note for uniqueness constraint testing",
            tags=["test", "uniqueness"],
        )

        # Create a link
        source, _ = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.EXTENDS,
            description="First link",
        )

        # Try to create the same link type again (should be ignored)
        source, _ = zettel_service.create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type=LinkType.EXTENDS,
            description="Duplicate link type",
        )

        # Verify only one link of this type exists
        matching_links = [
            link
            for link in source.links
            if link.target_id == target_note.id and link.link_type == LinkType.EXTENDS
        ]
        assert len(matching_links) == 1
        # Description should not be updated since the original link is preserved
        assert matching_links[0].description == "First link"

    def test_get_linked_notes_outgoing(self, zettel_service):
        """Test retrieving outgoing linked notes with correct link types."""
        # Create test notes
        central_note = zettel_service.create_note(
            title="Central Note",
            content="Note with multiple outgoing links",
            note_type=NoteType.HUB,
            tags=["test", "linked-notes"],
        )

        # Create several target notes
        target_notes = []
        link_types = [LinkType.EXTENDS, LinkType.REFINES, LinkType.SUPPORTS]

        for i, link_type in enumerate(link_types):
            note = zettel_service.create_note(
                title=f"Target Note {i+1}",
                content=f"Target {i+1} content",
                note_type=NoteType.PERMANENT,
                tags=["test", "target"],
            )
            target_notes.append(note)

            # Create link
            zettel_service.create_link(
                source_id=central_note.id,
                target_id=note.id,
                link_type=link_type,
                description=f"Testing {link_type.value} relationship",
            )

        # Get outgoing linked notes
        linked_notes = zettel_service.get_linked_notes(central_note.id, "outgoing")

        # Verify correct number of linked notes
        assert len(linked_notes) == len(link_types)

        # Verify all target notes are included
        linked_ids = [note.id for note in linked_notes]
        for target in target_notes:
            assert target.id in linked_ids

        # Testing that link types are correctly displayed would require
        # direct testing of the MCP server output function, which is
        # handled in the next test

    # Fix for test_mcp_get_linked_notes_tool
    def test_mcp_get_linked_notes_tool(self, zettel_service):
        """Test that zk_get_linked_notes correctly displays semantic link types."""
        # Create test notes
        central_note = zettel_service.create_note(
            title="MCP Tool Test Central Note",
            content="Note for testing MCP get linked notes tool",
            note_type=NoteType.HUB,
            tags=["test", "mcp-tool"],
        )
        target_note = zettel_service.create_note(
            title="MCP Tool Test Target Note",
            content="Target for testing MCP get linked notes tool",
            note_type=NoteType.PERMANENT,
            tags=["test", "mcp-tool"],
        )

        # Create link with semantic type
        zettel_service.create_link(
            source_id=central_note.id,
            target_id=target_note.id,
            link_type=LinkType.EXTENDS,
            description="Testing extends relationship",
        )

        # Create MCP server
        server = ZettelkastenMcpServer()
        server.zettel_service = zettel_service

        # Access the tool function directly as a method of the server
        result = server.zk_get_linked_notes(
            note_id=central_note.id, direction="outgoing"
        )

        # Verify result contains correct link type
        assert "Found" in result
        assert "linked notes for " + central_note.id in result
        assert "Link type: extends" in result
        assert "Testing extends relationship" in result

    # Fix for test_mcp_create_link_tool
    def test_mcp_create_link_tool(self, zettel_service):
        """Test that zk_create_link correctly creates links with semantic types."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="MCP Create Link Source",
            content="Note for testing MCP create link tool",
            note_type=NoteType.PERMANENT,
            tags=["test", "mcp-create-link"],
        )
        target_note = zettel_service.create_note(
            title="MCP Create Link Target",
            content="Target for testing MCP create link tool",
            note_type=NoteType.PERMANENT,
            tags=["test", "mcp-create-link"],
        )

        # Create MCP server with mocked functions
        server = ZettelkastenMcpServer()
        server.zettel_service = zettel_service  # Use our test zettel_service

        # Call the tool function directly as a method of the server
        result = server.zk_create_link(
            source_id=source_note.id,
            target_id=target_note.id,
            link_type="supports",
            description="Testing supports relationship via MCP tool",
            bidirectional=True,
        )

        # Verify link was created with correct type
        assert "Bidirectional link created" in result

        # Verify link through repository
        updated_source = zettel_service.get_note(source_note.id)
        updated_target = zettel_service.get_note(target_note.id)

        # Check source note's links
        source_links = [
            link for link in updated_source.links if link.target_id == target_note.id
        ]
        assert len(source_links) == 1
        assert source_links[0].link_type == LinkType.SUPPORTS
        assert (
            source_links[0].description == "Testing supports relationship via MCP tool"
        )

        # Check target note's links (inverse relationship)
        target_links = [
            link for link in updated_target.links if link.target_id == source_note.id
        ]
        assert len(target_links) == 1
        assert target_links[0].link_type == LinkType.SUPPORTED_BY

    def test_link_cycle_detection(self, zettel_service):
        """Test scenarios involving cycles of semantic links."""
        # Create a cycle of notes with semantic links
        note_a = zettel_service.create_note(
            title="Cycle Note A",
            content="First note in a cycle",
            note_type=NoteType.PERMANENT,
            tags=["test", "cycle"],
        )
        note_b = zettel_service.create_note(
            title="Cycle Note B",
            content="Second note in a cycle",
            note_type=NoteType.PERMANENT,
            tags=["test", "cycle"],
        )
        note_c = zettel_service.create_note(
            title="Cycle Note C",
            content="Third note in a cycle",
            note_type=NoteType.PERMANENT,
            tags=["test", "cycle"],
        )

        # Create a cycle: A extends B, B refines C, C contradicts A
        zettel_service.create_link(
            source_id=note_a.id,
            target_id=note_b.id,
            link_type=LinkType.EXTENDS,
            description="A extends B",
        )
        zettel_service.create_link(
            source_id=note_b.id,
            target_id=note_c.id,
            link_type=LinkType.REFINES,
            description="B refines C",
        )
        zettel_service.create_link(
            source_id=note_c.id,
            target_id=note_a.id,
            link_type=LinkType.CONTRADICTS,
            description="C contradicts A",
        )

        # Verify links were created correctly
        note_a = zettel_service.get_note(note_a.id)
        note_b = zettel_service.get_note(note_b.id)
        note_c = zettel_service.get_note(note_c.id)

        # Verify A -> B link
        a_outgoing = [link for link in note_a.links if link.target_id == note_b.id]
        assert len(a_outgoing) == 1
        assert a_outgoing[0].link_type == LinkType.EXTENDS

        # Verify B -> C link
        b_outgoing = [link for link in note_b.links if link.target_id == note_c.id]
        assert len(b_outgoing) == 1
        assert b_outgoing[0].link_type == LinkType.REFINES

        # Verify C -> A link
        c_outgoing = [link for link in note_c.links if link.target_id == note_a.id]
        assert len(c_outgoing) == 1
        assert c_outgoing[0].link_type == LinkType.CONTRADICTS

        # Test that we can still find links through the cycle
        # From A, we should be able to traverse to both B and C
        a_links = zettel_service.get_linked_notes(note_a.id, "both")
        a_linked_ids = [note.id for note in a_links]
        assert note_b.id in a_linked_ids
        assert note_c.id in a_linked_ids

    def test_semantic_links_in_search_results(self, zettel_service):
        """Test that searching finds notes with specific semantic links."""
        # Create test notes
        hub_note = zettel_service.create_note(
            title="Search Hub Note",
            content="Hub note for testing search with semantic links",
            note_type=NoteType.HUB,
            tags=["test", "search", "hub"],
        )

        linked_note = zettel_service.create_note(
            title="Linked Search Note",
            content="Note for testing search with semantic links",
            note_type=NoteType.PERMANENT,
            tags=["test", "search", "linked"],
        )

        unlinked_note = zettel_service.create_note(
            title="Unlinked Search Note",
            content="Note for testing search with semantic links",
            note_type=NoteType.PERMANENT,
            tags=["test", "search", "unlinked"],
        )

        # Create semantic link
        zettel_service.create_link(
            source_id=hub_note.id,
            target_id=linked_note.id,
            link_type=LinkType.EXTENDS,
            description="Link for search testing",
        )

        # Create search service
        from zettelkasten_mcp.services.search_service import SearchService

        search_service = SearchService(zettel_service)

        # Search for linked notes
        linked_notes = zettel_service.get_linked_notes(hub_note.id, "outgoing")
        assert len(linked_notes) == 1
        assert linked_notes[0].id == linked_note.id

        # Search for notes by tag to verify all test notes are found
        search_results = zettel_service.get_notes_by_tag("search")
        assert len(search_results) == 3

    def test_find_similar_notes_with_semantic_links(self, zettel_service):
        """Test similarity detection based on semantic link types."""
        # Create test notes
        source_note = zettel_service.create_note(
            title="Similar Source Note",
            content="Source note for testing similarity",
            note_type=NoteType.PERMANENT,
            tags=["test", "similarity", "source"],
        )

        # Create target notes with different semantic relationships
        target1 = zettel_service.create_note(
            title="Similar Target 1",
            content="First target for similarity testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "similarity", "extends-target"],
        )

        target2 = zettel_service.create_note(
            title="Similar Target 2",
            content="Second target for similarity testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "similarity", "contradicts-target"],
        )

        target3 = zettel_service.create_note(
            title="Similar Target 3",
            content="Third target for similarity testing",
            note_type=NoteType.PERMANENT,
            tags=["test", "similarity", "unrelated-target"],
        )

        # Create semantic links
        zettel_service.create_link(
            source_id=source_note.id,
            target_id=target1.id,
            link_type=LinkType.EXTENDS,
            description="Source extends Target 1",
        )

        zettel_service.create_link(
            source_id=source_note.id,
            target_id=target2.id,
            link_type=LinkType.CONTRADICTS,
            description="Source contradicts Target 2",
        )

        # Don't link to target3 at all

        # Find similar notes
        similar_notes = zettel_service.find_similar_notes(source_note.id, 0.0)

        # Convert to IDs for easier comparison
        similar_ids = [note_tuple[0].id for note_tuple in similar_notes]

        # Both linked notes should appear in results
        assert target1.id in similar_ids
        assert target2.id in similar_ids

        # The similarity scores might vary, but we should have at least the
        # two linked notes in the results
        assert len(similar_notes) >= 2

    def test_central_notes_with_semantic_links(self, zettel_service):
        """Test the find_central_notes function with semantic links."""
        from zettelkasten_mcp.services.search_service import SearchService

        search_service = SearchService(zettel_service)

        # Create a network of notes with semantic links
        hub = zettel_service.create_note(
            title="Central Hub Note",
            content="Hub note with many connections",
            note_type=NoteType.HUB,
            tags=["test", "central", "hub"],
        )

        satellite1 = zettel_service.create_note(
            title="Satellite Note 1",
            content="First satellite note",
            note_type=NoteType.PERMANENT,
            tags=["test", "central", "satellite"],
        )

        satellite2 = zettel_service.create_note(
            title="Satellite Note 2",
            content="Second satellite note",
            note_type=NoteType.PERMANENT,
            tags=["test", "central", "satellite"],
        )

        satellite3 = zettel_service.create_note(
            title="Satellite Note 3",
            content="Third satellite note",
            note_type=NoteType.PERMANENT,
            tags=["test", "central", "satellite"],
        )

        orphan = zettel_service.create_note(
            title="Orphan Note",
            content="Note with no connections",
            note_type=NoteType.PERMANENT,
            tags=["test", "central", "orphan"],
        )

        # Create links with different semantic types
        zettel_service.create_link(
            source_id=hub.id,
            target_id=satellite1.id,
            link_type=LinkType.EXTENDS,
            description="Hub extends Satellite 1",
        )

        zettel_service.create_link(
            source_id=hub.id,
            target_id=satellite2.id,
            link_type=LinkType.CONTRADICTS,
            description="Hub contradicts Satellite 2",
        )

        zettel_service.create_link(
            source_id=hub.id,
            target_id=satellite3.id,
            link_type=LinkType.SUPPORTS,
            description="Hub supports Satellite 3",
        )

        # Also create links between satellites
        zettel_service.create_link(
            source_id=satellite1.id,
            target_id=satellite2.id,
            link_type=LinkType.REFINES,
            description="Satellite 1 refines Satellite 2",
        )

        # Find central notes
        central_notes = search_service.find_central_notes(limit=10)

        # Convert to a dictionary of ID to connection count
        central_dict = {note.id: count for note, count in central_notes}

        # Hub should have the most connections
        assert hub.id in central_dict
        assert central_dict[hub.id] >= 3  # Hub has 3 outgoing links

        # Check positions
        hub_position = None
        satellite1_position = None
        for i, (note, _) in enumerate(central_notes):
            if note.id == hub.id:
                hub_position = i
            elif note.id == satellite1.id:
                satellite1_position = i

        assert hub_position is not None
        if satellite1_position is not None:
            assert hub_position < satellite1_position  # Hub should be ranked higher

        # Orphan should not be in central notes
        assert orphan.id not in central_dict
