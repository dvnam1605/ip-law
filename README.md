# 🏛️ SHTT Legal RAG: Vietnamese Intellectual Property Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**SHTT Legal RAG** (Sở Hữu Trí Tuệ) is a specialized AI-powered assistant designed for Vietnamese Intellectual Property Law. It leverages a **Hybrid RAG (Retrieval-Augmented Generation)** architecture, combining Graph Databases and Vector Search to provide accurate, context-aware legal advice and trademark search capabilities.

---

## 🚀 Key Features

- **Hybrid RAG Architecture**: Integrates **Qdrant** (Vector Search) for semantic similarity and **Neo4j** (Graph Database) for structured legal relationships and context expansion.
- **Vietnamese IP Law Focus**: Optimized for Vietnamese legal documents using specialized embedding models (PhoBERT-based).
- **Verdict Analysis**: Advanced processing of court verdicts with automated metadata extraction.
- **Trademark Search & Crawler**: Integrated tools for crawling and searching Vietnamese trademark databases.
- **Streaming Response**: Real-time message streaming for a smooth user experience.
- **Comprehensive Benchmarking**: Built-in evaluation module following the ViLeXa/Zalo AI challenge standards.

---

## 🏗️ Architecture

The system uses a unique hybrid approach to ensure high precision and recall in legal retrieval:

1.  **Neo4j Pre-filter**: Filters document IDs based on structured metadata (status, effective date, etc.).
2.  **Qdrant Vector Search**: Performs high-speed ANN (Approximate Nearest Neighbor) search on the filtered ID list.
3.  **Context Expansion**: Re-traverses the Graph in Neo4j to retrieve neighboring chunks (`NEXT`/`PREV` relationships) to provide the LLM with full context.
4.  **LLM Synthesis**: Uses Google Gemini AI to synthesize the final answer from retrieved context and chat history.

---

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.12+)
- **Vector DB**: Qdrant
- **Graph DB**: Neo4j
- **Relational DB**: PostgreSQL (Auth & Trademark data)
- **AI/ML**: LangChain, Sentence-Transformers (PhoBERT), Google Gemini API
- **Crawler**: Playwright

### Frontend
- **Framework**: React 19 + Vite
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **Data Viz**: Recharts

---

## 📦 Installation

### Prerequisites
- [Docker & Docker Compose](https://www.docker.com/)
- [Conda](https://docs.conda.io/en/latest/) or Python 3.10+
- [Node.js & npm](https://nodejs.org/)

### 1. Infrastructure Setup
Spin up the database cluster (PostgreSQL, Neo4j, Qdrant):
```bash
docker-compose up -d
```
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)
- **Qdrant Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)

### 2. Backend Setup
```bash
# Create environment
conda create -n shtt python=3.12 -y
conda activate shtt

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd frontend
npm install
```

### 4. Configuration
Create a `.env` file in the root directory:
```env
# Database
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=legal_rag

# AI Keys
GEMINI_API_KEY=your_gemini_key

# Qdrant
QDRANT_URL=http://localhost:6333
```

---

## 🏃 Quick Start

### 1. Data Ingestion
Populate your databases with legal documents and verdicts:
```bash
# Ingest Legal Documents
python scripts/run_legal_pipeline.py

# Ingest Court Verdicts
python scripts/run_verdict_pipeline.py
```

### 2. Run Servers
**Backend:**
```bash
cd backend/api
python app.py
```
*API Docs: [http://localhost:1605/docs](http://localhost:1605/docs)*

**Frontend:**
```bash
cd frontend
npm run dev
```
*UI: [http://localhost:5173](http://localhost:5173)*

---

## 📡 API Documentation

### Key Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/query/stream` | Streamed RAG query for legal questions. |
| `POST` | `/api/smart/query/stream` | Intelligent router between Legal, Verdict, and Trademark. |
| `GET`  | `/api/trademark/search` | Search for registered trademarks. |
| `POST` | `/api/auth/login` | User authentication and JWT issuance. |

---

## 📊 Evaluation (ViLeXa-style)

The project includes a robust benchmarking tool to measure retrieval performance:
```bash
python -m benchmarks.run_eval \
       --mode legal \
       --data-dir data/internal_legal_benchmark \
       --k-values 1,5,10
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---


