import json
from datetime import datetime
from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

from .settings import settings


class MilvusStore:
    def __init__(self) -> None:
        self.collection_name = settings.milvus_collection
        self.vector_dim = settings.vector_dim
        self.collection: Collection | None = None

    def connect(self) -> None:
        connections.connect(alias="default", host=settings.milvus_host, port=settings.milvus_port)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not utility.has_collection(self.collection_name):
            self._create_collection()
        else:
            self.collection = Collection(self.collection_name)
            self._handle_existing_collection_dim()

        self.collection.load()

    def _create_collection(self) -> None:
        fields = [
            FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="chunk_id", dtype=DataType.INT64),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="source_path", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.vector_dim),
        ]
        schema = CollectionSchema(fields=fields, description="Integrated enterprise search chunks")
        self.collection = Collection(name=self.collection_name, schema=schema)
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 1024},
        }
        self.collection.create_index(field_name="embedding", index_params=index_params)

    def _handle_existing_collection_dim(self) -> None:
        assert self.collection is not None

        embedding_field = next((f for f in self.collection.schema.fields if f.name == "embedding"), None)
        if embedding_field is None:
            raise ValueError("Milvus collection schema does not contain 'embedding' field")

        field_dim = embedding_field.params.get("dim")
        if field_dim is None:
            raise ValueError("Milvus 'embedding' field does not define vector dimension")

        current_dim = int(field_dim)
        if current_dim != int(self.vector_dim):
            if settings.milvus_auto_migrate_dim:
                self._backup_and_recreate_collection(current_dim)
                return

            raise ValueError(
                "Milvus collection dimension mismatch: "
                f"collection_dim={field_dim}, VECTOR_DIM={self.vector_dim}. "
                "Use matching VECTOR_DIM or set MILVUS_AUTO_MIGRATE_DIM=true."
            )

    def _backup_and_recreate_collection(self, old_dim: int) -> None:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        backup_name = f"{self.collection_name}_{settings.milvus_backup_prefix}_{old_dim}d_{timestamp}"

        if utility.has_collection(backup_name):
            backup_name = f"{backup_name}_1"

        utility.rename_collection(self.collection_name, backup_name)
        self._create_collection()

    def upsert_chunks(
        self,
        document_id: str,
        title: str,
        source_path: str,
        metadata: dict[str, Any],
        chunks: list[str],
        vectors: list[list[float]],
    ) -> int:
        assert self.collection is not None

        self.collection.delete(expr=f'document_id == "{document_id}"')

        rows = [
            [document_id for _ in chunks],
            list(range(len(chunks))),
            [title for _ in chunks],
            chunks,
            [source_path for _ in chunks],
            [json.dumps(metadata, ensure_ascii=True) for _ in chunks],
            vectors,
        ]
        self.collection.insert(rows)
        self.collection.flush()
        return len(chunks)

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        assert self.collection is not None

        results = self.collection.search(
            data=[query_vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 10}},
            limit=top_k,
            output_fields=["document_id", "title", "text", "source_path", "metadata_json"],
        )

        hits: list[dict[str, Any]] = []
        for hit in results[0]:
            entity = hit.entity
            metadata_json = entity.get("metadata_json") or "{}"
            hits.append(
                {
                    "document_id": entity.get("document_id"),
                    "title": entity.get("title") or "",
                    "text_snippet": entity.get("text") or "",
                    "source_path": entity.get("source_path") or "",
                    "metadata": json.loads(metadata_json),
                    "score": float(hit.score),
                }
            )
        return hits
