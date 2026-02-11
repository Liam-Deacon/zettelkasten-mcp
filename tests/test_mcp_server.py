# tests/test_mcp_server.py
"""Tests for the MCP server implementation."""
from unittest.mock import MagicMock, call, patch

import pytest

from zettelkasten_mcp.models.schema import LinkType, NoteType
from zettelkasten_mcp.server.mcp_server import ZettelkastenMcpServer


class TestMcpServer:
    """Tests for the ZettelkastenMcpServer class."""

    def setup_method(self):
        """Set up test environment before each test."""
        # Capture the tool decorator functions when registering
        self.registered_tools = {}

        # Create a mock for FastMCP
        self.mock_mcp = MagicMock()

        # Mock the tool decorator to capture registered functions BEFORE server creation
        def mock_tool_decorator(*args, **kwargs):
            def tool_wrapper(func):
                # Store the function with its name
                name = kwargs.get("name")
                self.registered_tools[name] = func
                return func

            return tool_wrapper

        self.mock_mcp.tool = mock_tool_decorator

        # Mock the ZettelService and SearchService
        self.mock_zettel_service = MagicMock()
        self.mock_search_service = MagicMock()

        # Create patchers for FastMCP, ZettelService, and SearchService
        self.mcp_patcher = patch(
            "zettelkasten_mcp.server.mcp_server.FastMCP", return_value=self.mock_mcp
        )
        self.zettel_patcher = patch(
            "zettelkasten_mcp.server.mcp_server.ZettelService",
            return_value=self.mock_zettel_service,
        )
        self.search_patcher = patch(
            "zettelkasten_mcp.server.mcp_server.SearchService",
            return_value=self.mock_search_service,
        )

        # Start the patchers
        self.mcp_patcher.start()
        self.zettel_patcher.start()
        self.search_patcher.start()

        # Create a server instance AFTER setting up the mocks
        self.server = ZettelkastenMcpServer()

    def teardown_method(self):
        """Clean up after each test."""
        self.mcp_patcher.stop()
        self.zettel_patcher.stop()
        self.search_patcher.stop()

    def test_server_initialization(self):
        """Test server initialization."""
        # Check services are initialized
        assert self.mock_zettel_service.initialize.called
        assert self.mock_search_service.initialize.called

    def test_create_note_tool(self):
        """Test the zk_create_note tool."""
        # Check the tool is registered
        assert "zk_create_note" in self.registered_tools
        # Set up return value for create_note
        mock_note = MagicMock()
        mock_note.id = "test123"
        self.mock_zettel_service.create_note.return_value = mock_note
        # Call the tool function directly
        create_note_func = self.registered_tools["zk_create_note"]
        result = create_note_func(
            title="Test Note",
            content="Test content",
            note_type="permanent",
            tags="tag1, tag2",
        )
        # Verify result
        assert "successfully" in result
        assert mock_note.id in result
        # Verify service call
        self.mock_zettel_service.create_note.assert_called_with(
            title="Test Note",
            content="Test content",
            note_type=NoteType.PERMANENT,
            tags=["tag1", "tag2"],
        )

    def test_get_note_tool(self):
        """Test the zk_get_note tool."""
        # Check the tool is registered
        assert "zk_get_note" in self.registered_tools

        # Set up mock note
        mock_note = MagicMock()
        mock_note.id = "test123"
        mock_note.title = "Test Note"
        mock_note.content = "Test content"
        mock_note.note_type = NoteType.PERMANENT
        mock_note.created_at.isoformat.return_value = "2023-01-01T12:00:00"
        mock_note.updated_at.isoformat.return_value = "2023-01-01T12:30:00"
        mock_tag1 = MagicMock()
        mock_tag1.name = "tag1"
        mock_tag2 = MagicMock()
        mock_tag2.name = "tag2"
        mock_note.tags = [mock_tag1, mock_tag2]
        mock_note.links = []

        # Set up return value for get_note
        self.mock_zettel_service.get_note.return_value = mock_note

        # Call the tool function directly
        get_note_func = self.registered_tools["zk_get_note"]
        result = get_note_func(identifier="test123")

        # Verify result
        assert "# Test Note" in result
        assert "ID: test123" in result
        assert "Test content" in result

        # Verify service call
        self.mock_zettel_service.get_note.assert_called_with("test123")

    def test_create_link_tool(self):
        """Test the zk_create_link tool."""
        # Check the tool is registered
        assert "zk_create_link" in self.registered_tools

        # Set up mock notes
        source_note = MagicMock()
        source_note.id = "source123"
        target_note = MagicMock()
        target_note.id = "target456"

        # Set up return value for create_link
        self.mock_zettel_service.create_link.return_value = (source_note, target_note)

        # Call the tool function directly
        create_link_func = self.registered_tools["zk_create_link"]
        result = create_link_func(
            source_id="source123",
            target_id="target456",
            link_type="extends",
            description="Test link",
            bidirectional=True,
        )

        # Verify result
        assert "Bidirectional link created" in result
        assert "source123" in result
        assert "target456" in result

        # Verify service call
        self.mock_zettel_service.create_link.assert_called_with(
            source_id="source123",
            target_id="target456",
            link_type=LinkType.EXTENDS,
            description="Test link",
            bidirectional=True,
        )

    def test_search_notes_tool(self):
        """Test the zk_search_notes tool."""
        # Check the tool is registered
        assert "zk_search_notes" in self.registered_tools

        # Set up mock notes
        mock_note1 = MagicMock()
        mock_note1.id = "note1"
        mock_note1.title = "Note 1"
        mock_note1.content = "This is note 1 content"
        mock_tag1 = MagicMock()
        mock_tag1.name = "tag1"
        mock_tag2 = MagicMock()
        mock_tag2.name = "tag2"
        mock_note1.tags = [mock_tag1, mock_tag2]
        mock_note1.created_at.strftime.return_value = "2023-01-01"

        mock_note2 = MagicMock()
        mock_note2.id = "note2"
        mock_note2.title = "Note 2"
        mock_note2.content = "This is note 2 content"
        # mock_note2.tags = [MagicMock(name="tag1")]
        mock_tag1 = MagicMock()
        mock_tag1.name = "tag1"
        mock_note2.tags = [mock_tag1]
        mock_note2.created_at.strftime.return_value = "2023-01-02"

        # Set up mock search results
        mock_result1 = MagicMock()
        mock_result1.note = mock_note1
        mock_result2 = MagicMock()
        mock_result2.note = mock_note2

        self.mock_search_service.search_combined.return_value = [
            mock_result1,
            mock_result2,
        ]

        # Call the tool function directly
        search_notes_func = self.registered_tools["zk_search_notes"]
        result = search_notes_func(
            query="test query", tags="tag1, tag2", note_type="permanent", limit=10
        )

        # Verify result
        assert "Found 2 matching notes" in result
        assert "Note 1" in result
        assert "Note 2" in result

        # Verify service call
        self.mock_search_service.search_combined.assert_called_with(
            text="test query", tags=["tag1", "tag2"], note_type=NoteType.PERMANENT
        )

    def test_error_handling(self):
        """Test error handling in the server."""
        # Test ValueError handling
        value_error = ValueError("Invalid input")
        result = self.server.format_error_response(value_error)
        assert "Error: Invalid input" in result

        # Test IOError handling
        io_error = IOError("File not found")
        result = self.server.format_error_response(io_error)
        assert "Error: File not found" in result

        # Test general exception handling
        general_error = Exception("Something went wrong")
        result = self.server.format_error_response(general_error)
        assert "Error: Something went wrong" in result
