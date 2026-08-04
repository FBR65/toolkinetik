"""RAG Manager — lazy-initialized LanceDB + HuggingFace embeddings.

Provides document search capabilities by loading a HuggingFace
embedding model on demand and indexing documents in LanceDB.
"""

from __future__ import annotations

from typing import Any


class RagManager:
    """Manages RAG initialization with LanceDB + HuggingFace embeddings.

    Embeddings are loaded lazily — only when a RAG query is first received —
    to avoid loading a large model on every request.
    """

    def __init__(self) -> None:
        self._embedder: Any | None = None
        self._db: Any = None
        self._table: Any = None
        self._initialized = False

    def initialize(self) -> None:
        """Lazy-load the embedding model and LanceDB table."""
        if self._initialized:
            return
        try:
            import lancedb
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer("sentence-transformers/all-MiniLLM-L6-v2")
            self._db = lancedb.connect("data/lancedb")
            try:
                self._table = self._db.open_table("toolkinetik_docs")
            except Exception:
                schema = lancedb.schema(
                    {
                        "vector": "{embedding}",
                        "text": "str",
                        "source": "str",
                    },
                    mode="create",
                )
                self._table = self._db.create_table("toolkinetik_docs", schema=schema)
            self._initialized = True
        except ImportError:
            self._initialized = False

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search indexed documents for *query*."""
        if not self._initialized:
            self.initialize()
        if not self._initialized or self._embedder is None or self._table is None:
            return []
        query_vec = self._embedder.encode([query]).tolist()[0]
        results = self._table.search(query_vec).limit(top_k).to_list()
        return results

    @property
    def is_ready(self) -> bool:
        """Return True if the RAG system is initialized."""
        return self._initialized
