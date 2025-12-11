"""MongoDB-backed repository for note storage."""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional, Sequence, Union

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from zettelkasten_mcp.config import config
from zettelkasten_mcp.models.schema import Link, LinkType, Note, NoteType, Tag
from zettelkasten_mcp.storage.base import Repository

logger = logging.getLogger(__name__)


class MongoNoteRepository(Repository[Note]):
    """Repository implementation that stores notes in MongoDB."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        database: Optional[str] = None,
        collection: Optional[str] = None,
    ):
        if not (mongodb_uri or config.mongodb_uri):
            raise ValueError(
                "MongoDB URI is required when using the Mongo storage backend. "
                "Set MONGODB_URI or pass mongodb_uri explicitly."
            )

        self._client = MongoClient(mongodb_uri or config.mongodb_uri)
        db_name = database or config.mongodb_database
        coll_name = collection or config.mongodb_collection
        self._db = self._client[db_name]
        self.collection: Collection = self._db[coll_name]

        # Ensure indexes for common lookups
        self.collection.create_index("id", unique=True)
        self.collection.create_index("title")
        self.collection.create_index("note_type")
        self.collection.create_index("tags")
        self.collection.create_index("links.target_id")

        logger.info(
            "MongoNoteRepository initialised using database '%s' and collection '%s'",
            db_name,
            coll_name,
        )

    @staticmethod
    def _note_to_document(note: Note) -> Dict[str, Any]:
        """Convert a Note object to a MongoDB document."""
        return {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "note_type": note.note_type.value,
            "tags": [tag.name for tag in note.tags],
            "links": [
                {
                    "source_id": link.source_id,
                    "target_id": link.target_id,
                    "link_type": link.link_type.value,
                    "description": link.description,
                    "created_at": link.created_at,
                }
                for link in note.links
            ],
            "created_at": note.created_at,
            "updated_at": note.updated_at,
            "metadata": note.metadata,
        }

    @staticmethod
    def _document_to_note(doc: Dict[str, Any]) -> Note:
        """Convert a MongoDB document to a Note object."""
        tags = [Tag(name=tag) for tag in doc.get("tags", [])]
        links = [
            Link(
                source_id=str(doc.get("id")),
                target_id=str(link.get("target_id")),
                link_type=LinkType(link.get("link_type", LinkType.REFERENCE.value)),
                description=link.get("description"),
                created_at=link.get("created_at", datetime.datetime.now()),
            )
            for link in doc.get("links", [])
        ]

        return Note(
            id=str(doc.get("id")),
            title=doc.get("title", ""),
            content=doc.get("content", ""),
            note_type=NoteType(doc.get("note_type", NoteType.PERMANENT.value)),
            tags=tags,
            links=links,
            created_at=doc.get("created_at", datetime.datetime.now()),
            updated_at=doc.get("updated_at", datetime.datetime.now()),
            metadata=doc.get("metadata", {}),
        )

    # CRUD interface -----------------------------------------------------
    def create(self, entity: Note) -> Note:
        note = entity
        if not note.id:
            from zettelkasten_mcp.models.schema import generate_id

            note.id = generate_id()

        document = self._note_to_document(note)
        try:
            self.collection.insert_one(document)
        except PyMongoError as exc:
            raise IOError(f"Failed to insert note into MongoDB: {exc}") from exc
        return note

    def get(self, id: str) -> Optional[Note]:
        document = self.collection.find_one({"id": id})
        return self._document_to_note(document) if document else None

    def get_all(self) -> List[Note]:
        return [self._document_to_note(doc) for doc in self.collection.find()]

    def get_by_title(self, title: str) -> Optional[Note]:
        document = self.collection.find_one({"title": title})
        return self._document_to_note(document) if document else None

    def update(self, entity: Note) -> Note:
        note = entity
        note.updated_at = datetime.datetime.now()
        document = self._note_to_document(note)
        result = self.collection.update_one({"id": note.id}, {"$set": document})
        if result.matched_count == 0:
            raise ValueError(f"Note with ID {note.id} does not exist")
        return note

    def delete(self, id: str) -> None:
        result = self.collection.delete_one({"id": id})
        if result.deleted_count == 0:
            raise ValueError(f"Note with ID {id} does not exist")

    # Query helpers ------------------------------------------------------
    def search(self, **kwargs: Any) -> List[Note]:
        query: Dict[str, Any] = {}

        if "content" in kwargs:
            query["content"] = {"$regex": kwargs["content"], "$options": "i"}
        if "title" in kwargs:
            query["title"] = {"$regex": kwargs["title"], "$options": "i"}
        if "note_type" in kwargs:
            note_type = (
                kwargs["note_type"].value
                if isinstance(kwargs["note_type"], NoteType)
                else kwargs["note_type"]
            )
            query["note_type"] = str(note_type)
        if "tag" in kwargs:
            query["tags"] = kwargs["tag"]
        if "tags" in kwargs:
            tags = kwargs["tags"]
            if isinstance(tags, Sequence):
                query["tags"] = {"$in": list(tags)}
        if "linked_to" in kwargs:
            query["links.target_id"] = kwargs["linked_to"]
        if "linked_from" in kwargs:
            query["links.target_id"] = kwargs["linked_from"]
        if "created_after" in kwargs:
            query["created_at"] = {"$gte": kwargs["created_after"]}
        if "created_before" in kwargs:
            query.setdefault("created_at", {})
            query["created_at"]["$lte"] = kwargs["created_before"]
        if "updated_after" in kwargs:
            query["updated_at"] = {"$gte": kwargs["updated_after"]}
        if "updated_before" in kwargs:
            query.setdefault("updated_at", {})
            query["updated_at"]["$lte"] = kwargs["updated_before"]

        return [self._document_to_note(doc) for doc in self.collection.find(query)]

    def find_by_tag(self, tag: Union[str, Tag]) -> List[Note]:
        tag_name = tag.name if isinstance(tag, Tag) else tag
        return [
            self._document_to_note(doc)
            for doc in self.collection.find({"tags": tag_name})
        ]

    def find_linked_notes(
        self, note_id: str, direction: str = "outgoing"
    ) -> List[Note]:
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("direction must be 'outgoing', 'incoming', or 'both'")

        results: Dict[str, Note] = {}

        # Outgoing links (note -> target)
        if direction in {"outgoing", "both"}:
            note = self.get(note_id)
            if note:
                for link in note.links:
                    target = self.get(link.target_id)
                    if target:
                        results[target.id] = target

        # Incoming links (source -> note)
        if direction in {"incoming", "both"}:
            for doc in self.collection.find({"links.target_id": note_id}):
                if doc.get("id") == note_id:
                    continue
                note = self._document_to_note(doc)
                results[note.id] = note

        return list(results.values())

    def get_all_tags(self) -> List[Tag]:
        pipeline = [{"$unwind": "$tags"}, {"$group": {"_id": "$tags"}}]
        tag_names = [doc["_id"] for doc in self.collection.aggregate(pipeline)]
        return [Tag(name=name) for name in sorted(tag_names)]

    def rebuild_index(self) -> None:
        """No-op for Mongo backend; kept for parity with filesystem repository."""
        return None
