# 🏛️ Legal RAG Chatbot - Tư vấn Pháp luật Việt Nam

Hệ thống RAG (Retrieval-Augmented Generation) cho tư vấn pháp luật và bản án sở hữu trí tuệ Việt Nam. Hệ thống sử dụng kiến trúc lai (Hybrid Architecture) kết hợp **Qdrant** (Vector Search) và **Neo4j** (Graph Database) cùng với Gemini AI.

## 📁 Cấu trúc dự án

```text
shtt/
├── backend/
│   ├── api/                    # FastAPI application
│   │   └── app.py              # API entrypoint & routes registration
│   ├── core/
│   │   ├── pipeline/           # RAG pipelines
│   │   │   ├── rag_pipeline.py
│   │   │   ├── verdict_rag_pipeline.py
│   │   │   └── trademark_pipeline.py
│   │   ├── smart_router.py     # Router legal/verdict/trademark/combined
│   │   ├── config.py           # Centralized settings
│   │   └── security.py         # JWT + password utilities
│   ├── runtime/
│   │   └── retrievers/         # Runtime retrievers (Neo4j + Qdrant hybrid)
│   ├── tooling/                # Offline ingestion/crawler scripts as importable modules
│   ├── chunking/               # Document processing & Upload
│   │   ├── legal_chunker.py    # Chunking & Embedding pháp luật
│   │   ├── verdict_chunker.py  # Chunking & Embedding bản án
│   │   └── verdict_extractors.py # Trích xuất metadata bản án
│   ├── services/               # Service layer used by API routes
├── frontend/                   # React + Vite Chat App UI
├── data/
│   ├── models/                 # Vietnamese embedding model
│   └── processed/              # Source legal & verdict TXT files
├── scripts/                    # Pipeline runners
│   ├── run_legal_pipeline.py   # Chạy pipeline pháp luật
│   └── run_verdict_pipeline.py # Chạy pipeline bản án
├── benchmarks/                 # ViLeXa-style retrieval benchmark module
│   ├── run_eval.py             # CLI benchmark legal/verdict retrievers
│   └── README.md               # Hướng dẫn format dataset + chạy benchmark
├── docker-compose.yml          # Neo4j, Qdrant, PostgreSQL
├── requirements.txt            # Python dependencies cho Backend
├── frontend/package.json       # Node dependencies cho Frontend
└── .env                        # Environment variables
```

## 🚀 Cài đặt

### 1. Khởi động các Database (Neo4j, Qdrant, Postgres)

```bash
docker-compose up -d
```
- Qdrant Dashboard: http://localhost:6333/dashboard
- Neo4j Browser: http://localhost:7474

### 2. Cài đặt Backend

```bash
# Tạo môi trường conda
conda create -n shtt python=3.12
conda activate shtt

# Cài đặt dependencies
pip install -r requirements.txt
```

### 3. Cài đặt Frontend

```bash
cd frontend
npm install
```

### 4. Cấu hình environment variables

Tạo file `.env` tại thư mục gốc:

```env
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=legal_rag
```

## 🔄 Data Pipeline (Hybrid Architecture)

Quy trình nhập dữ liệu (Ingestion) được chia thành 2 bước để tận dụng sức mạnh của cả Qdrant và Neo4j:

### Chạy các scripts tự động

```bash
# 1. Pipeline cho Pháp luật
python scripts/run_legal_pipeline.py

# 2. Pipeline cho Bản án
python scripts/run_verdict_pipeline.py
```

### Luồng xử lý chi tiết (Bên trong scripts):
1. **Chunking & Embedding (Qdrant)**
   - Đọc files TXT, chia chunk (Rule-based cho luật, NLP cho bản án).
   - Tạo embedding (độ dài 1024) bằng mô hình tiếng Việt.
   - Upload trực tiếp vector lên **Qdrant** cùng ID của chunk (`chunk_id`).
   - Lưu metadata ra file JSON làm đầu vào cho bước 2.
2. **Graph Ingestion (Neo4j)**
   - Lấy metadata và danh sách IDs từ JSON ở bước 1.
   - Tạo nodes (Document, Verdict, Chunk) vào Neo4j (nhưng **không lưu embedding** để giảm tải dung lượng).
   - Khởi tạo các relationships (thứ tự chunk `NEXT`, quan hệ `PART_OF`, v.v.).

## 🔍 Hybrid RAG Pipeline Flow

Khi User hỏi một câu hỏi:

```text
1. User Query
       ↓
2. Neo4j Pre-filter (Chỉ lấy IDs của các chunks thuộc các documents hợp lệ: status=active, năm ban hành...)
       ↓
3. Qdrant Vector Search (ANN Search cực nhanh chỉ trên các list ID đã filter từ bước 2)
       ↓
4. Neo4j Context Expansion (Lấy chunk_ids trả về từ Qdrant, vào lại Neo4j lấy FULL_TEXT của chunk + các chunks lân cận (NEXT/PREV) để mở rộng ngữ cảnh)
       ↓
5. LLM Synthesis (Gửi cho Gemini AI kèm Lịch sử Chat)
       ↓
6. Response Streaming (Frontend render chữ theo dạng stream)
```

## 🔧 Chạy ứng dụng

### 1. Chạy Backend (API Server)
```bash
cd backend/api
conda activate shtt
python app.py
```
API Documentation: http://localhost:1605/docs

### 2. Chạy Frontend (Chat UI)
```bash
cd frontend
npm run dev
```
Giao diện ứng dụng: http://localhost:5173

## ⚙️ Cấu hình Backend

| Variable | Default | Mô tả |
|----------|---------|-------|
| `GEMINI_API_KEY` | - | API key cho Gemini |
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Kết nối Neo4j |
| `QDRANT_URL` | `http://192.168.1.199:6333`| Kết nối Qdrant |
| `QDRANT_LEGAL_COLLECTION` | `legal_chunks` | Tên collection pháp luật trong Qdrant |
| `QDRANT_VERDICT_COLLECTION` | `verdict_chunks` | Tên collection bản án trong Qdrant |

## 📊 Benchmark Retrieval (ViLeXa-style)

Project hiện có module benchmark riêng tại [benchmarks/README.md](benchmarks/README.md), dùng format qrels giống ViLeXa/Zalo.

### Chạy benchmark Legal

```bash
python -m benchmarks.run_eval \
       --mode legal \
       --data-dir data/your_benchmark \
       --k-values 1,3,5,10,20
```

### Chạy benchmark Verdict

```bash
python -m benchmarks.run_eval \
       --mode verdict \
       --data-dir data/your_benchmark \
       --k-values 1,3,5,10,20
```

Lưu ý mapping ID khi tạo qrels:
- `legal` dùng `chunk_id`.
- `verdict` dùng `vchunk_id`.

## 📝 License

MIT License
