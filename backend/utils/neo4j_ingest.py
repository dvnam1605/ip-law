import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import hashlib
from datetime import datetime

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("⚠️ neo4j package not installed. Run: pip install neo4j")


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "aa")

CHUNKS_JSON = "./chunks_output_v2.json"
EMBEDDINGS_JSON = "./chunks_output_v2_with_embeddings.json"


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        if not NEO4J_AVAILABLE:
            raise ImportError("neo4j package is required. Install with: pip install neo4j")
        
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._verify_connection()
    
    def _verify_connection(self):
        with self.driver.session() as session:
            result = session.run("RETURN 1 as test")
            record = result.single()
            if record["test"] == 1:
                print("✅ Connected to Neo4j successfully")
    
    def close(self):
        self.driver.close()
    
    def run_query(self, query: str, parameters: Dict = None) -> List[Dict]:
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def run_write(self, query: str, parameters: Dict = None):
        with self.driver.session() as session:
            session.execute_write(lambda tx: tx.run(query, parameters or {}))


def setup_schema(client: Neo4jClient):
    print("\n📋 Setting up Neo4j schema...")
    
    constraints = [
        "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
        "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    ]
    
    for constraint in constraints:
        try:
            client.run_write(constraint)
            print(f"  ✓ Created constraint")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  ⏭ Constraint already exists")
            else:
                print(f"  ⚠️ {e}")
    
    indexes = [
        "CREATE INDEX chunk_doc_id IF NOT EXISTS FOR (c:Chunk) ON (c.doc_id)",
        "CREATE INDEX chunk_dieu IF NOT EXISTS FOR (c:Chunk) ON (c.dieu)",
        "CREATE INDEX chunk_type IF NOT EXISTS FOR (c:Chunk) ON (c.chunk_type)",
        "CREATE INDEX doc_status IF NOT EXISTS FOR (d:Document) ON (d.status)",
        "CREATE INDEX doc_type IF NOT EXISTS FOR (d:Document) ON (d.doc_type)",
        "CREATE INDEX doc_effective_date IF NOT EXISTS FOR (d:Document) ON (d.effective_date)",
    ]
    
    for index in indexes:
        try:
            client.run_write(index)
            print(f"  ✓ Created index")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  ⏭ Index already exists")
            else:
                print(f"  ⚠️ {e}")
    
    print("✅ Schema setup complete")


def setup_vector_index(client: Neo4jClient, dimension: int = 1024):
    print(f"\n🔢 Setting up vector index (dimension={dimension})...")
    
    check_query = """
    SHOW INDEXES 
    WHERE name = 'chunk_embedding_index'
    """
    
    try:
        result = client.run_query(check_query)
        if result:
            print("  ⏭ Vector index already exists")
            return
    except:
        pass
    
    vector_index_query = f"""
    CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS
    FOR (c:Chunk) ON (c.embedding)
    OPTIONS {{
        indexConfig: {{
            `vector.dimensions`: {dimension},
            `vector.similarity_function`: 'cosine'
        }}
    }}
    """
    
    try:
        client.run_write(vector_index_query)
        print("  ✓ Created vector index")
    except Exception as e:
        print(f"  ⚠️ Vector index error: {e}")
        print("  💡 Note: Vector index requires Neo4j 5.11+ with vector search plugin")


def load_effective_dates(filepath: str) -> Dict[str, Dict]:
    if not os.path.exists(filepath):
        print(f"⚠️ {filepath} not found, using default metadata")
        return {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    mapping = {}
    for doc in data.get('documents', []):
        filename = doc.get('filename')
        if filename:
            mapping[filename] = doc
    
    print(f"📅 Loaded effective dates for {len(mapping)} documents")
    return mapping


def load_chunks(filepath: str) -> List[Dict]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Chunks file not found: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    print(f"📄 Loaded {len(chunks)} chunks from {filepath}")
    return chunks


def generate_chunk_id(content: str, doc_id: str, chunk_index: int) -> str:
    hash_input = f"{doc_id}_{chunk_index}_{content[:100]}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:16]


def ingest_documents(client: Neo4jClient, chunks: List[Dict]):
    print("\n📁 Ingesting Document nodes...")
    
    docs = {}
    for chunk in chunks:
        meta = chunk.get('metadata', {})
        filename = meta.get('title', '')
        
        if filename not in docs:
            docs[filename] = {
                'doc_id': meta.get('doc_number') or filename,
                'filename': filename,
                'doc_name': meta.get('doc_name', ''),
                'doc_type': meta.get('doc_type', ''),
                'doc_number': meta.get('doc_number', ''),
                'issuing_agency': meta.get('issuing_agency'),
                'signing_date': meta.get('signing_date'),
                'effective_date': meta.get('effective_date'),
                'status': meta.get('status', 'active'),
            }
    
    query = """
    UNWIND $docs AS doc
    MERGE (d:Document {doc_id: doc.doc_id})
    SET d.filename = doc.filename,
        d.doc_name = doc.doc_name,
        d.doc_type = doc.doc_type,
        d.doc_number = doc.doc_number,
        d.issuing_agency = doc.issuing_agency,
        d.signing_date = doc.signing_date,
        d.effective_date = doc.effective_date,
        d.status = doc.status,
        d.updated_at = datetime()
    """
    
    client.run_write(query, {'docs': list(docs.values())})
    print(f"  ✓ Created/updated {len(docs)} Document nodes")
    
    return docs


def ingest_chunks(client: Neo4jClient, chunks: List[Dict], docs: Dict[str, Dict], batch_size: int = 100):
    print(f"\n📝 Ingesting {len(chunks)} Chunk nodes...")
    
    chunk_data = []
    for chunk in chunks:
        meta = chunk.get('metadata', {})
        filename = meta.get('title', '')
        doc_id = docs.get(filename, {}).get('doc_id', filename)
        chunk_index = meta.get('chunk_index', 0)
        
        chunk_data.append({
            'chunk_id': generate_chunk_id(chunk.get('content', ''), doc_id, chunk_index),
            'doc_id': doc_id,
            'content': chunk.get('content', ''),
            'chunk_index': chunk_index,
            'chunk_type': meta.get('chunk_type', 'content'),
            'phan': meta.get('phan'),
            'chuong': meta.get('chuong'),
            'chuong_title': meta.get('chuong_title'),
            'muc': meta.get('muc'),
            'dieu': meta.get('dieu'),
            'dieu_title': meta.get('dieu_title'),
            'is_continuation': meta.get('is_continuation', False),
        })
    
    query = """
    UNWIND $chunks AS chunk
    MERGE (c:Chunk {chunk_id: chunk.chunk_id})
    SET c.doc_id = chunk.doc_id,
        c.content = chunk.content,
        c.chunk_index = chunk.chunk_index,
        c.chunk_type = chunk.chunk_type,
        c.phan = chunk.phan,
        c.chuong = chunk.chuong,
        c.chuong_title = chunk.chuong_title,
        c.muc = chunk.muc,
        c.dieu = chunk.dieu,
        c.dieu_title = chunk.dieu_title,
        c.is_continuation = chunk.is_continuation,
        c.updated_at = datetime()
    WITH c, chunk
    MATCH (d:Document {doc_id: chunk.doc_id})
    MERGE (c)-[:PART_OF]->(d)
    """
    
    for i in range(0, len(chunk_data), batch_size):
        batch = chunk_data[i:i+batch_size]
        client.run_write(query, {'chunks': batch})
        print(f"  ✓ Processed {min(i+batch_size, len(chunk_data))}/{len(chunk_data)} chunks")
    
    return chunk_data


def create_next_relationships(client: Neo4jClient):
    print("\n🔗 Creating NEXT relationships...")
    
    query = """
    MATCH (c1:Chunk)
    WITH c1
    ORDER BY c1.doc_id, c1.chunk_index
    WITH collect(c1) AS chunks
    UNWIND range(0, size(chunks)-2) AS i
    WITH chunks[i] AS current, chunks[i+1] AS next
    WHERE current.doc_id = next.doc_id
    MERGE (current)-[:NEXT]->(next)
    """
    
    client.run_write(query)
    
    count_query = "MATCH ()-[r:NEXT]->() RETURN count(r) as count"
    result = client.run_query(count_query)
    count = result[0]['count'] if result else 0
    print(f"  ✓ Created {count} NEXT relationships")


def ingest_embeddings(client: Neo4jClient, embeddings_file: str, batch_size: int = 50):
    if not os.path.exists(embeddings_file):
        print(f"⚠️ Embeddings file not found: {embeddings_file}")
        return
    
    print(f"\n🔢 Ingesting embeddings from {embeddings_file}...")
    
    with open(embeddings_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    embedding_data = []
    for item in data:
        if 'embedding' in item and 'metadata' in item:
            meta = item['metadata']
            doc_id = meta.get('doc_number', meta.get('title', ''))
            chunk_index = meta.get('chunk_index', 0)
            chunk_id = generate_chunk_id(item.get('content', ''), doc_id, chunk_index)
            
            embedding_data.append({
                'chunk_id': chunk_id,
                'embedding': item['embedding']
            })
    
    if not embedding_data:
        print("  ⚠️ No embeddings found in file")
        return
    
    query = """
    UNWIND $data AS item
    MATCH (c:Chunk {chunk_id: item.chunk_id})
    SET c.embedding = item.embedding
    """
    
    for i in range(0, len(embedding_data), batch_size):
        batch = embedding_data[i:i+batch_size]
        client.run_write(query, {'data': batch})
        print(f"  ✓ Updated {min(i+batch_size, len(embedding_data))}/{len(embedding_data)} embeddings")


def print_query_examples():
    print("\n" + "="*60)
    print("📖 EXAMPLE CYPHER QUERIES FOR LEGAL RAG")
    print("="*60)
    
    examples = [
        {
            "name": "1. Filter active documents by effective date",
            "query": """
MATCH (c:Chunk)-[:PART_OF]->(d:Document)
WHERE d.status = 'active' 
  AND d.effective_date <= date('2024-01-01')
  AND (d.expiry_date IS NULL OR d.expiry_date > date('2024-01-01'))
RETURN c.chunk_id, c.content, d.doc_name
LIMIT 10
"""
        },
        {
            "name": "2. Vector search with pre-filtering (requires embeddings)",
            "query": """
// First filter by legal validity
MATCH (c:Chunk)-[:PART_OF]->(d:Document)
WHERE d.status = 'active' AND d.doc_type = 'Luật'
WITH c, d

// Then do vector search (example with placeholder)
// CALL db.index.vector.queryNodes('chunk_embedding_index', 10, $query_embedding)
// YIELD node, score
RETURN c.chunk_id, c.dieu, c.content, d.doc_name
LIMIT 10
"""
        },
        {
            "name": "3. Get chunk with context (NEXT neighbors)",
            "query": """
MATCH (c:Chunk {dieu: 'Điều 4'})-[:PART_OF]->(d:Document {doc_type: 'Luật'})
OPTIONAL MATCH (prev)-[:NEXT]->(c)
OPTIONAL MATCH (c)-[:NEXT]->(next)
RETURN 
    prev.content AS previous_chunk,
    c.content AS current_chunk,
    next.content AS next_chunk,
    d.doc_name AS document
"""
        },
        {
            "name": "4. Find all Điều in a Chương",
            "query": """
MATCH (c:Chunk)-[:PART_OF]->(d:Document)
WHERE c.chuong = 'Chương I' AND d.doc_number = '50/2005/QH11'
RETURN DISTINCT c.dieu, c.dieu_title
ORDER BY c.chunk_index
"""
        },
        {
            "name": "5. Search chunks by keyword with document filtering",
            "query": """
MATCH (c:Chunk)-[:PART_OF]->(d:Document)
WHERE c.content CONTAINS 'quyền sở hữu trí tuệ'
  AND d.status = 'active'
  AND d.doc_type IN ['Luật', 'Nghị định']
RETURN c.dieu, c.content, d.doc_name, d.effective_date
LIMIT 20
"""
        }
    ]
    
    for ex in examples:
        print(f"\n{'─'*40}")
        print(f"📌 {ex['name']}")
        print(f"{'─'*40}")
        print(ex['query'])


def get_stats(client: Neo4jClient):
    print("\n📊 Database Statistics")
    print("="*40)
    
    queries = [
        ("Documents", "MATCH (d:Document) RETURN count(d) as count"),
        ("Chunks", "MATCH (c:Chunk) RETURN count(c) as count"),
        ("PART_OF relationships", "MATCH ()-[r:PART_OF]->() RETURN count(r) as count"),
        ("NEXT relationships", "MATCH ()-[r:NEXT]->() RETURN count(r) as count"),
        ("Chunks with embeddings", "MATCH (c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) as count"),
        ("Active documents", "MATCH (d:Document {status: 'active'}) RETURN count(d) as count"),
    ]
    
    for name, query in queries:
        try:
            result = client.run_query(query)
            count = result[0]['count'] if result else 0
            print(f"  {name}: {count}")
        except Exception as e:
            print(f"  {name}: Error - {e}")


def main():
    print("="*60)
    print("🗄️  NEO4J LEGAL RAG INGEST")
    print("="*60)
    
    # Check if neo4j is available
    if not NEO4J_AVAILABLE:
        print("\n❌ Please install neo4j: pip install neo4j")
        return
    
    # Connect to Neo4j
    print(f"\n🔌 Connecting to Neo4j at {NEO4J_URI}...")
    try:
        client = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        print("\n💡 Make sure Neo4j is running and credentials are correct")
        print("   Set environment variables: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        return
    
    try:
        # Setup schema
        setup_schema(client)
        
        # Load data
        chunks = load_chunks(CHUNKS_JSON)
        
        # Ingest
        docs = ingest_documents(client, chunks)
        chunk_data = ingest_chunks(client, chunks, docs)
        create_next_relationships(client)
        
        # Setup vector index
        setup_vector_index(client, dimension=1024)
        
        # Ingest embeddings if available
        if os.path.exists(EMBEDDINGS_JSON):
            ingest_embeddings(client, EMBEDDINGS_JSON)
        else:
            print(f"\n💡 To add embeddings, save them to {EMBEDDINGS_JSON} and re-run")
        
        # Show stats
        get_stats(client)
        
        # Print query examples
        print_query_examples()
        
        print("\n" + "="*60)
        print("✅ INGEST COMPLETE!")
        print("="*60)
        
    finally:
        client.close()


if __name__ == "__main__":
    main()
