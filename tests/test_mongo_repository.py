"""Tests for the MongoDB-backed repository."""

import copy
import re
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from zettelkasten_mcp.models.schema import LinkType, Note, NoteType, Tag
from zettelkasten_mcp.services.search_service import SearchService
from zettelkasten_mcp.services.zettel_service import ZettelService
from zettelkasten_mcp.storage.mongo_repository import MongoNoteRepository


# --- Minimal fake pymongo client ------------------------------------------------
class FakeCollection:
    def __init__(self) -> None:
        self._docs: List[Dict[str, Any]] = []

    def create_index(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
        return None

    def insert_one(self, doc: Dict[str, Any]) -> SimpleNamespace:
        if any(existing.get("id") == doc.get("id") for existing in self._docs):
            raise Exception("duplicate id")
        self._docs.append(copy.deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    def find_one(self, filt: Dict[str, Any]) -> Dict[str, Any] | None:
        for doc in self.find(filt):
            return doc
        return None

    def _get_field_values(self, doc: Dict[str, Any], key: str) -> List[Any]:
        parts = key.split(".")
        values: List[Any] = [doc]
        for part in parts:
            next_values: List[Any] = []
            for val in values:
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, dict):
                            next_val = item.get(part)
                            if next_val is not None:
                                next_values.append(next_val)
                        else:
                            next_values.append(item)
                elif isinstance(val, dict):
                    next_val = val.get(part)
                    if next_val is not None:
                        next_values.append(next_val)
            values = next_values
        # Flatten any remaining list wrappers for direct comparisons
        flattened: List[Any] = []
        for val in values:
            if isinstance(val, list):
                flattened.extend(val)
            else:
                flattened.append(val)
        return flattened

    def _match(self, doc: Dict[str, Any], filt: Dict[str, Any]) -> bool:
        for key, value in filt.items():
            if key == "$or":
                if not any(self._match(doc, sub) for sub in value):
                    return False
                continue

            values = self._get_field_values(doc, key)
            if isinstance(value, dict):
                if "$regex" in value:
                    pattern = value["$regex"]
                    flags = (
                        re.IGNORECASE
                        if value.get("$options", "").lower().find("i") >= 0
                        else 0
                    )
                    if not any(
                        isinstance(v, str) and re.search(pattern, v, flags)
                        for v in values
                    ):
                        return False
                if "$in" in value:
                    if not any(v in value["$in"] for v in values):
                        return False
                if "$gte" in value:
                    if not any(v >= value["$gte"] for v in values if v is not None):
                        return False
                if "$lte" in value:
                    if not any(v <= value["$lte"] for v in values if v is not None):
                        return False
                continue

            if not any(v == value for v in values):
                return False
        return True

    def find(self, filt: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        filt = filt or {}
        return [copy.deepcopy(doc) for doc in self._docs if self._match(doc, filt)]

    def update_one(
        self, filt: Dict[str, Any], update: Dict[str, Any]
    ) -> SimpleNamespace:
        matched = 0
        for doc in self._docs:
            if self._match(doc, filt):
                matched += 1
                if "$set" in update:
                    doc.update(copy.deepcopy(update["$set"]))
        return SimpleNamespace(matched_count=matched, modified_count=matched)

    def delete_one(self, filt: Dict[str, Any]) -> SimpleNamespace:
        for idx, doc in enumerate(self._docs):
            if self._match(doc, filt):
                self._docs.pop(idx)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Support the simple unwind/group pipeline used in get_all_tags
        if pipeline == [{"$unwind": "$tags"}, {"$group": {"_id": "$tags"}}]:
            tags = set()
            for doc in self._docs:
                for tag in doc.get("tags", []):
                    tags.add(tag)
            return [{"_id": tag} for tag in tags]
        return []

    def estimated_document_count(self) -> int:  # pragma: no cover
        return len(self._docs)


class FakeDatabase:
    def __init__(self) -> None:
        self._collections: Dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


class FakeMongoClient:
    def __init__(self) -> None:
        self._databases: Dict[str, FakeDatabase] = {}

    def __getitem__(self, name: str) -> FakeDatabase:
        if name not in self._databases:
            self._databases[name] = FakeDatabase()
        return self._databases[name]


# --- Fixtures ------------------------------------------------------------------
@pytest.fixture
def mongo_repo(monkeypatch) -> MongoNoteRepository:
    client = FakeMongoClient()

    def _fake_client(_uri: str, *_args: Any, **_kwargs: Any) -> FakeMongoClient:
        return client

    monkeypatch.setattr(
        "zettelkasten_mcp.storage.mongo_repository.MongoClient", _fake_client
    )
    return MongoNoteRepository(
        mongodb_uri="mongodb://example",
        database="test_db",
        collection="notes",
    )


# --- Tests ---------------------------------------------------------------------
def test_mongo_repository_crud(mongo_repo: MongoNoteRepository) -> None:
    note = Note(
        title="Mongo Test",
        content="Doc content",
        note_type=NoteType.PERMANENT,
        tags=[Tag(name="alpha")],
    )
    saved = mongo_repo.create(note)
    fetched = mongo_repo.get(saved.id)
    assert fetched is not None
    assert fetched.title == "Mongo Test"

    saved.title = "Updated"
    saved.tags = [Tag(name="beta")]
    mongo_repo.update(saved)
    fetched_after = mongo_repo.get(saved.id)
    assert fetched_after and fetched_after.title == "Updated"
    assert {t.name for t in fetched_after.tags} == {"beta"}

    mongo_repo.delete(saved.id)
    assert mongo_repo.get(saved.id) is None


def test_mongo_repository_search_and_tags(mongo_repo: MongoNoteRepository) -> None:
    py = mongo_repo.create(
        Note(
            title="Python",
            content="Python is great",
            note_type=NoteType.PERMANENT,
            tags=[Tag(name="python"), Tag(name="lang")],
        )
    )
    js = mongo_repo.create(
        Note(
            title="JavaScript",
            content="JS for web",
            note_type=NoteType.PERMANENT,
            tags=[Tag(name="javascript"), Tag(name="lang")],
        )
    )

    assert mongo_repo.search(title="Python")[0].id == py.id
    content_hits = mongo_repo.search(content="web")
    assert any(note.id == js.id for note in content_hits)

    tag_hits = mongo_repo.find_by_tag("lang")
    assert {n.id for n in tag_hits} == {py.id, js.id}

    tags = mongo_repo.get_all_tags()
    assert {t.name for t in tags} == {"python", "javascript", "lang"}


def test_mongo_repository_links(mongo_repo: MongoNoteRepository) -> None:
    source = mongo_repo.create(
        Note(
            title="Source",
            content="links out",
            tags=[Tag(name="src")],
        )
    )
    target = mongo_repo.create(
        Note(
            title="Target",
            content="links in",
            tags=[Tag(name="tgt")],
        )
    )

    source.add_link(
        target_id=target.id, link_type=LinkType.REFERENCE, description="ref"
    )
    mongo_repo.update(source)

    outgoing = mongo_repo.find_linked_notes(source.id, "outgoing")
    assert len(outgoing) == 1 and outgoing[0].id == target.id

    incoming = mongo_repo.find_linked_notes(target.id, "incoming")
    assert len(incoming) == 1 and incoming[0].id == source.id

    both = mongo_repo.find_linked_notes(target.id, "both")
    assert {n.id for n in both} == {source.id}


def test_search_service_fallback_with_mongo(mongo_repo: MongoNoteRepository) -> None:
    a = mongo_repo.create(Note(title="A", content="alpha"))
    b = mongo_repo.create(Note(title="B", content="bravo"))

    a.add_link(target_id=b.id, link_type=LinkType.REFERENCE)
    mongo_repo.update(a)

    service = ZettelService(repository=mongo_repo)
    search = SearchService(service)

    orphans = search.find_orphaned_notes()
    assert orphans == []

    central = search.find_central_notes(limit=5)
    counts = {note.id: count for note, count in central}
    assert counts.get(a.id) == 1
    assert counts.get(b.id) == 1
