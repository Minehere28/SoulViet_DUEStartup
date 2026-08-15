import hashlib
import math
import os
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from langchain_core.embeddings import Embeddings
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore


class LocalHashEmbeddings(Embeddings):
    """Small deterministic embedding for private, offline preference retrieval."""

    def __init__(self, dimensions=256):
        self.dimensions = dimensions

    def _embed(self, text):
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\w+", str(text).casefold(), flags=re.UNICODE)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


class AgentMemory:
    def __init__(self, root=None):
        root = Path(root or os.getenv("SOULVIET_AGENT_DB_DIR", ".soulviet"))
        root.mkdir(parents=True, exist_ok=True)
        checkpoint_connection = sqlite3.connect(
            root / "checkpoints.sqlite3", check_same_thread=False
        )
        store_connection = sqlite3.connect(
            root / "memories.sqlite3", check_same_thread=False
        )
        checkpoint_connection.execute("PRAGMA journal_mode=WAL")
        checkpoint_connection.execute("PRAGMA busy_timeout=5000")
        store_connection.execute("PRAGMA journal_mode=WAL")
        store_connection.execute("PRAGMA busy_timeout=5000")
        self.checkpointer = SqliteSaver(checkpoint_connection)
        self.store = SqliteStore(
            store_connection,
            index={
                "embed": LocalHashEmbeddings(),
                "dims": 256,
                "fields": ["text"],
            },
        )
        self.store.setup()
        store_connection.commit()

    @staticmethod
    def namespace(user_id):
        return ("users", str(user_id), "preferences")

    def search(self, user_id, query, limit=5):
        if not query:
            return []
        items = self.store.search(
            self.namespace(user_id), query=query, limit=limit
        )
        return [
            {
                "id": item.key,
                **item.value,
                "score": round(float(item.score or 0), 4),
            }
            for item in items
        ]

    def list(self, user_id, limit=20):
        return [
            {"id": item.key, **item.value}
            for item in self.store.search(
                self.namespace(user_id), limit=limit
            )
        ]

    def save(self, user_id, text, kind="preference", source="explicit"):
        memory_id = str(uuid4())
        value = {"text": text, "kind": kind, "source": source}
        self.store.put(self.namespace(user_id), memory_id, value)
        return {"id": memory_id, **value}

    def forget(self, user_id, memory_id):
        self.store.delete(self.namespace(user_id), memory_id)
