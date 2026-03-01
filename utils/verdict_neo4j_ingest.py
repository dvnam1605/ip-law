import json
import os
import hashlib
from typing import List, Dict

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "dvnam1605")

CHUNKS_JSON = "/home/namdv/shtt/chunking/verdict_chunks.json"
EMBEDDINGS_JSON = "/home/namdv/shtt/chunking/verdict_chunks_with_embeddings.json"


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._verify()

    def _verify(self):
        with self.driver.session() as session:
            if session.run("RETURN 1 as t").single()["t"] == 1:
                print("✅ Connected to Neo4j")

    def close(self):
        self.driver.close()

    def run_query(self, query: str, params: Dict = None) -> List[Dict]:
        with self.driver.session() as session:
            return [r.data() for r in session.run(query, params or {})]

    def run_write(self, query: str, params: Dict = None):
        with self.driver.session() as session:
            session.execute_write(lambda tx: tx.run(query, params or {}))


def _generate_vchunk_id(content: str, verdict_id: str, chunk_index: int) -> str:
    hash_input = f"v_{verdict_id}_{chunk_index}_{content[:100]}"
    return "v_" + hashlib.md5(hash_input.encode()).hexdigest()[:16]


def setup_schema(client: Neo4jClient):
    print("\n📋 Setting up Verdict schema...")
    statements = [
        "CREATE CONSTRAINT verdict_id IF NOT EXISTS FOR (v:Verdict) REQUIRE v.verdict_id IS UNIQUE",
        "CREATE CONSTRAINT vchunk_id IF NOT EXISTS FOR (vc:VerdictChunk) REQUIRE vc.vchunk_id IS UNIQUE",
        "CREATE INDEX vchunk_verdict_id IF NOT EXISTS FOR (vc:VerdictChunk) ON (vc.verdict_id)",
        "CREATE INDEX vchunk_section_type IF NOT EXISTS FOR (vc:VerdictChunk) ON (vc.section_type)",
        "CREATE INDEX verdict_ip_type IF NOT EXISTS FOR (v:Verdict) ON (v.ip_types_str)",
        "CREATE INDEX verdict_trial_level IF NOT EXISTS FOR (v:Verdict) ON (v.trial_level)",
        "CREATE INDEX verdict_judgment_date IF NOT EXISTS FOR (v:Verdict) ON (v.judgment_date)",
    ]
    for stmt in statements:
        try:
            client.run_write(stmt)
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"  ⚠️ {e}")
    print("✅ Schema ready")


def setup_vector_index(client: Neo4jClient, dimension: int = 1024):
    try:
        if client.run_query("SHOW INDEXES WHERE name = 'verdict_chunk_embedding_index'"):
            return
    except Exception:
        pass

    try:
        client.run_write(f"""
        CREATE VECTOR INDEX verdict_chunk_embedding_index IF NOT EXISTS
        FOR (vc:VerdictChunk) ON (vc.embedding)
        OPTIONS {{indexConfig: {{
            `vector.dimensions`: {dimension},
            `vector.similarity_function`: 'cosine'
        }}}}
        """)
        print("✓ Created verdict vector index")
    except Exception as e:
        print(f"⚠️ Vector index error: {e}")


def load_chunks(filepath: str) -> List[Dict]:
    with open(filepath, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    print(f"📄 Loaded {len(chunks)} chunks from {filepath}")
    return chunks


def ingest_verdicts(client: Neo4jClient, chunks: List[Dict]) -> Dict:
    verdicts = {}
    for chunk in chunks:
        meta = chunk.get('metadata', {})
        filename = meta.get('filename', '')
        if filename in verdicts:
            continue

        verdict_id = meta.get('case_number') or filename
        ip_types = meta.get('ip_types', [])
        law_refs = meta.get('law_references', [])

        verdicts[filename] = {
            'verdict_id': verdict_id,
            'filename': filename,
            'case_number': meta.get('case_number', ''),
            'court_name': meta.get('court_name', ''),
            'judgment_date': meta.get('judgment_date', ''),
            'dispute_type': meta.get('dispute_type', ''),
            'trial_level': meta.get('trial_level', ''),
            'plaintiff': meta.get('plaintiff', ''),
            'defendant': meta.get('defendant', ''),
            'third_party': meta.get('third_party', ''),
            'ip_types': ip_types,
            'ip_types_str': ','.join(ip_types),
            'judges': meta.get('judges', ''),
            'law_references': law_refs,
            'law_references_str': '|'.join(law_refs[:20]),
            'summary': meta.get('summary', ''),
        }

    client.run_write("""
    UNWIND $verdicts AS v
    MERGE (vd:Verdict {verdict_id: v.verdict_id})
    SET vd += v, vd.updated_at = datetime()
    """, {'verdicts': list(verdicts.values())})
    print(f"  ✓ {len(verdicts)} Verdict nodes")
    return verdicts


def ingest_verdict_chunks(client: Neo4jClient, chunks: List[Dict], verdicts: Dict, batch_size: int = 100):
    chunk_data = []
    for chunk in chunks:
        meta = chunk.get('metadata', {})
        filename = meta.get('filename', '')
        verdict_id = verdicts.get(filename, {}).get('verdict_id', filename)
        chunk_index = meta.get('chunk_index', 0)

        chunk_data.append({
            'vchunk_id': _generate_vchunk_id(chunk.get('content', ''), verdict_id, chunk_index),
            'verdict_id': verdict_id,
            'content': chunk.get('content', ''),
            'chunk_index': chunk_index,
            'section_type': meta.get('section_type', 'header'),
            'party_role': meta.get('party_role', ''),
            'point_number': meta.get('point_number', ''),
            'item_number': meta.get('item_number', ''),
        })

    query = """
    UNWIND $chunks AS c
    MERGE (vc:VerdictChunk {vchunk_id: c.vchunk_id})
    SET vc += c, vc.updated_at = datetime()
    WITH vc, c
    MATCH (v:Verdict {verdict_id: c.verdict_id})
    MERGE (vc)-[:PART_OF_VERDICT]->(v)
    """
    for i in range(0, len(chunk_data), batch_size):
        client.run_write(query, {'chunks': chunk_data[i:i + batch_size]})
    print(f"  ✓ {len(chunk_data)} VerdictChunk nodes")
    return chunk_data


def create_next_relationships(client: Neo4jClient):
    client.run_write("""
    MATCH (vc1:VerdictChunk)
    WITH vc1 ORDER BY vc1.verdict_id, vc1.chunk_index
    WITH collect(vc1) AS chunks
    UNWIND range(0, size(chunks)-2) AS i
    WITH chunks[i] AS current, chunks[i+1] AS next
    WHERE current.verdict_id = next.verdict_id
    MERGE (current)-[:NEXT_IN_VERDICT]->(next)
    """)
    count = client.run_query("MATCH ()-[r:NEXT_IN_VERDICT]->() RETURN count(r) as c")
    print(f"  ✓ {count[0]['c'] if count else 0} NEXT_IN_VERDICT relationships")


def create_semantic_relationships(client: Neo4jClient):
    rels = [
        ("CÓ_TÌNH_TIẾT", "['fact', 'lower_court_decision']"),
        ("CÓ_NHẬN_ĐỊNH", "['reasoning']"),
        ("ĐÃ_TUYÊN_ÁN", "['decision_item', 'court_fee']"),
    ]
    for rel_type, section_types in rels:
        client.run_write(f"""
        MATCH (vc:VerdictChunk)-[:PART_OF_VERDICT]->(v:Verdict)
        WHERE vc.section_type IN {section_types}
        MERGE (vc)-[:{rel_type}]->(v)
        """)
        count = client.run_query(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as c")
        print(f"  ✓ {rel_type}: {count[0]['c'] if count else 0}")


def ingest_embeddings(client: Neo4jClient, filepath: str, batch_size: int = 50):
    if not os.path.exists(filepath):
        print(f"⚠️ Embeddings file not found: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    embedding_data = []
    for item in data:
        if 'embedding' not in item or 'metadata' not in item:
            continue
        meta = item['metadata']
        verdict_id = meta.get('case_number') or meta.get('filename', '')
        vchunk_id = _generate_vchunk_id(item.get('content', ''), verdict_id, meta.get('chunk_index', 0))
        embedding_data.append({'vchunk_id': vchunk_id, 'embedding': item['embedding']})

    for i in range(0, len(embedding_data), batch_size):
        client.run_write("""
        UNWIND $data AS item
        MATCH (vc:VerdictChunk {vchunk_id: item.vchunk_id})
        SET vc.embedding = item.embedding
        """, {'data': embedding_data[i:i + batch_size]})
    print(f"  ✓ {len(embedding_data)} embeddings ingested")


def print_stats(client: Neo4jClient):
    print("\n📊 Verdict DB Stats")
    for name, q in [
        ("Verdicts", "MATCH (v:Verdict) RETURN count(v) as c"),
        ("Chunks", "MATCH (vc:VerdictChunk) RETURN count(vc) as c"),
        ("With embeddings", "MATCH (vc:VerdictChunk) WHERE vc.embedding IS NOT NULL RETURN count(vc) as c"),
    ]:
        result = client.run_query(q)
        print(f"  {name}: {result[0]['c'] if result else 0}")


def main():
    print("⚖️  NEO4J VERDICT INGEST")
    client = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        setup_schema(client)
        chunks = load_chunks(CHUNKS_JSON)
        verdicts = ingest_verdicts(client, chunks)
        ingest_verdict_chunks(client, chunks, verdicts)
        create_next_relationships(client)
        create_semantic_relationships(client)
        setup_vector_index(client)
        if os.path.exists(EMBEDDINGS_JSON):
            ingest_embeddings(client, EMBEDDINGS_JSON)
        print_stats(client)
        print("\n✅ VERDICT INGEST COMPLETE!")
    finally:
        client.close()


if __name__ == "__main__":
    main()
