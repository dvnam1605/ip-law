"""
Trademark Neo4j Ingestion + Embedding
Import crawled trademark data into Neo4j with vector embeddings.
"""
import json
import os
import logging
from pathlib import Path
from typing import List, Dict

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)


class TrademarkNeo4jIngestor:
    """Ingest trademark records into Neo4j with embeddings for vector search."""

    def __init__(
        self,
        uri: str = None,
        user: str = None,
        password: str = None,
        embedding_model_path: str = None,
    ):
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j package required: pip install neo4j")

        self.uri = uri or os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "aa")

        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

        # Load embedding model
        self.embedding_model = None
        model_path = embedding_model_path or str(PROJECT_ROOT / "vietnamese_embedding")
        if ST_AVAILABLE and Path(model_path).exists():
            logger.info(f"Loading embedding model from {model_path}...")
            self.embedding_model = SentenceTransformer(model_path)
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            logger.info(f"Model loaded. Dimension: {self.embedding_dim}")
        else:
            logger.warning("Embedding model not available — will skip vector indexing")

    def close(self):
        self.driver.close()

    def _run_query(self, query: str, params: Dict = None):
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

    def setup_constraints_and_indexes(self):
        """Create Neo4j constraints and vector index for trademarks."""
        queries = [
            # Uniqueness constraint
            "CREATE CONSTRAINT trademark_reg_unique IF NOT EXISTS "
            "FOR (t:Trademark) REQUIRE t.registration_number IS UNIQUE",

            # Nice class node
            "CREATE CONSTRAINT nice_class_unique IF NOT EXISTS "
            "FOR (n:NiceClass) REQUIRE n.class_number IS UNIQUE",

            # Owner node
            "CREATE CONSTRAINT owner_unique IF NOT EXISTS "
            "FOR (o:TrademarkOwner) REQUIRE o.name IS UNIQUE",

            # Full-text index for fuzzy search
            "CREATE FULLTEXT INDEX trademark_brand_name_fulltext IF NOT EXISTS "
            "FOR (t:Trademark) ON EACH [t.brand_name, t.brand_name_lower]",
        ]

        for q in queries:
            try:
                self._run_query(q)
            except Exception as e:
                logger.warning(f"Index/constraint creation: {e}")

        # Vector index (Neo4j 5.x)
        if self.embedding_model:
            try:
                self._run_query(f"""
                    CREATE VECTOR INDEX trademark_embedding IF NOT EXISTS
                    FOR (t:Trademark) ON (t.embedding)
                    OPTIONS {{indexConfig: {{
                        `vector.dimensions`: {self.embedding_dim},
                        `vector.similarity_function`: 'cosine'
                    }}}}
                """)
                logger.info("Vector index created/exists")
            except Exception as e:
                logger.warning(f"Vector index: {e}")

    def _compute_embedding(self, record: Dict) -> List[float]:
        """Compute embedding from brand name + owner + nice classes."""
        if not self.embedding_model:
            return []
        text = f"{record['brand_name']} {record.get('owner_name', '')} "
        if record.get('nice_classes'):
            text += f"nhóm {' '.join(record['nice_classes'])}"
        embedding = self.embedding_model.encode(text)
        return embedding.tolist()

    def ingest_records(self, records: List[Dict], batch_size: int = 50):
        """
        Ingest trademark records into Neo4j.

        Expected record format:
        {
            "brand_name": "SAMSUNG",
            "owner_name": "Samsung Electronics Co., Ltd.",
            "owner_country": "Korea (Republic of)",
            "registration_number": "086139",
            "nice_classes": ["9", "11", "35"],
            "ipr_type": "National Trademark Registration",
            "country_of_filing": "Egypt",
            "status": "Registered (March 19, 1998)",
            "status_date": "March 19, 1998",
            "crawled_at": "2025-03-05T10:00:00"
        }
        """
        self.setup_constraints_and_indexes()

        total = len(records)
        logger.info(f"Ingesting {total} trademark records...")

        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]

            for rec in batch:
                # Compute embedding
                embedding = self._compute_embedding(rec)

                # Upsert Trademark node
                params = {
                    "brand_name": rec["brand_name"],
                    "brand_name_lower": rec["brand_name"].lower(),
                    "owner_name": rec.get("owner_name", ""),
                    "owner_country": rec.get("owner_country", ""),
                    "registration_number": rec.get("registration_number", ""),
                    "nice_classes": rec.get("nice_classes", []),
                    "ipr_type": rec.get("ipr_type", ""),
                    "country_of_filing": rec.get("country_of_filing", ""),
                    "status": rec.get("status", ""),
                    "status_date": rec.get("status_date", ""),
                    "crawled_at": rec.get("crawled_at", ""),
                    "embedding": embedding if embedding else None,
                }

                self._run_query("""
                    MERGE (t:Trademark {registration_number: $registration_number})
                    SET t.brand_name = $brand_name,
                        t.brand_name_lower = $brand_name_lower,
                        t.owner_name = $owner_name,
                        t.owner_country = $owner_country,
                        t.nice_classes = $nice_classes,
                        t.ipr_type = $ipr_type,
                        t.country_of_filing = $country_of_filing,
                        t.status = $status,
                        t.status_date = $status_date,
                        t.crawled_at = $crawled_at,
                        t.embedding = $embedding
                """, params)

                # Create Owner node + relationship
                if rec.get("owner_name"):
                    self._run_query("""
                        MERGE (o:TrademarkOwner {name: $owner_name})
                        SET o.country = $owner_country
                        WITH o
                        MATCH (t:Trademark {registration_number: $reg_num})
                        MERGE (t)-[:OWNED_BY]->(o)
                    """, {
                        "owner_name": rec["owner_name"],
                        "owner_country": rec.get("owner_country", ""),
                        "reg_num": rec["registration_number"],
                    })

                # Create NiceClass nodes + relationships
                for cls in rec.get("nice_classes", []):
                    self._run_query("""
                        MERGE (n:NiceClass {class_number: $class_num})
                        WITH n
                        MATCH (t:Trademark {registration_number: $reg_num})
                        MERGE (t)-[:IN_NICE_CLASS]->(n)
                    """, {
                        "class_num": cls,
                        "reg_num": rec["registration_number"],
                    })

            logger.info(f"  Ingested {min(i + batch_size, total)}/{total}")

        logger.info(f"✅ Ingestion complete: {total} records")

    def ingest_from_file(self, json_path: str, batch_size: int = 50):
        """Load records from a JSON file and ingest."""
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        logger.info(f"Loaded {len(records)} records from {json_path}")
        self.ingest_records(records, batch_size)


# ── CLI Entry Point ──────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Import trademark data into Neo4j")
    parser.add_argument("input_file", help="JSON file with trademark records")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    ingestor = TrademarkNeo4jIngestor()
    try:
        ingestor.ingest_from_file(args.input_file, args.batch_size)
    finally:
        ingestor.close()


if __name__ == "__main__":
    main()
