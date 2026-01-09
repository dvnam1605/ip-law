# 🏛️ Legal RAG Chatbot - Tư vấn Pháp luật Việt Nam

Hệ thống RAG (Retrieval-Augmented Generation) cho tư vấn pháp luật sở hữu trí tuệ Việt Nam, sử dụng Neo4j Graph Database và Gemini AI.

## 📁 Cấu trúc dự án

```
shtt/
├── api/                    # FastAPI application
│   └── main.py             # API endpoints
├── core/                   # Core business logic
│   └── rag_pipeline.py     # RAG pipeline với Gemini
├── utils/                  # Utilities
│   ├── neo4j_retriever.py  # Neo4j vector search
│   ├── neo4j_ingest.py     # Ingest data vào Neo4j
│   └── pdf_to_txt.py       # Convert PDF to text
├── chunking/               # Document processing
│   ├── legal_chunker.py    # Chunking logic v1
│   └── legal_chunker_v2.py # Chunking logic v2
├── vietnamese_embedding/   # Embedding model (gitignored)
├── tai_lieu_phap_luat/     # Source legal documents
├── docker-compose.yml      # Neo4j container
├── requirements.txt        # Python dependencies
└── .env                    # Environment variables
```

## 🚀 Cài đặt

### 1. Clone và cài đặt dependencies

```bash
# Tạo môi trường conda
conda create -n shtt python=3.12
conda activate shtt

# Cài đặt dependencies
pip install -r requirements.txt
```

### 2. Cấu hình environment variables

Tạo file `.env`:

```env
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Khởi động Neo4j

```bash
docker-compose up -d
```

Neo4j Browser: http://localhost:7474

### 4. Chuẩn bị Embedding Model

Download Vietnamese embedding model vào thư mục `vietnamese_embedding/`.

## 🔧 Chạy ứng dụng

### Chạy API Server

```bash
# Từ thư mục gốc
cd /path/to/shtt
conda activate shtt
python -m api.main

# Hoặc với uvicorn trực tiếp
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

API Documentation: http://localhost:8000/docs

### API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/` | Health check |
| GET | `/health` | Health check |
| POST | `/api/query` | Truy vấn pháp luật |
| GET | `/api/query?q=...` | Truy vấn (GET method) |

### Ví dụ Request

```bash
# POST request
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Điều kiện đăng ký nhãn hiệu ở Việt Nam?",
    "top_k": 5
  }'

# GET request
curl "http://localhost:8000/api/query?q=Điều%20kiện%20bảo%20hộ%20quyền%20tác%20giả&top_k=5"
```

### Response Format

```json
{
  "success": true,
  "query": "Điều kiện đăng ký nhãn hiệu ở Việt Nam?",
  "answer": "Theo Điều 87 - Luật Sở Hữu Trí Tuệ (Số văn bản: 50/2005/QH11)...",
  "sources": [
    {
      "doc_name": "Luật Sở Hữu Trí Tuệ",
      "doc_type": "Luật",
      "doc_number": "50/2005/QH11",
      "dieu": "Điều 87",
      "dieu_title": "Quyền đăng ký nhãn hiệu",
      "score": 0.8293
    }
  ],
  "retrieved_chunks": 5,
  "processing_time_ms": 1234.56
}
```

## 📊 Data Pipeline

### 1. Ingest Documents

```bash
# Convert PDF to text
python utils/pdf_to_txt.py

# Chunking documents
python chunking/legal_chunker_v2.py

# Ingest vào Neo4j
python utils/neo4j_ingest.py
```

### 2. Graph Schema

```
(:Document {doc_id, doc_name, doc_type, doc_number, effective_date, status})
    ↑
[:PART_OF]
    │
(:Chunk {chunk_id, content, dieu, dieu_title, chuong, embedding})
    │
[:NEXT]
    ↓
(:Chunk ...)
```

## 🔍 RAG Pipeline Flow

```
1. User Query
       ↓
2. Cypher Filter (status=active, effective_date)
       ↓
3. Vector Search (Neo4j + Embedding)
       ↓
4. Context Expansion (NEXT relationship)
       ↓
5. Gemini Generation
       ↓
6. Response với Source Citations
```

## ⚙️ Configuration

| Variable | Default | Mô tả |
|----------|---------|-------|
| `GEMINI_API_KEY` | - | API key cho Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model Gemini |
| `TOP_K_RETRIEVAL` | `5` | Số lượng chunks retrieve |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |

## 📝 License

MIT License
