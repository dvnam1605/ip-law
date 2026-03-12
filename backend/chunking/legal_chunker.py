import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from urllib.parse import unquote

from sentence_transformers import SentenceTransformer

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from langchain_text_splitters import RecursiveCharacterTextSplitter


QDRANT_URL = "http://192.168.1.199:6333"
COLLECTION_NAME = "Luật sở hữu trí tuệ"
EMBEDDING_MODEL_PATH = "./data/models/vietnamese_embedding"
VECTOR_SIZE = 1024

CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

TXT_FOLDER = "./output"
OUTPUT_JSON = "./chunks_output.json"


@dataclass
class DocumentMetadata:
    title: str
    doc_type: str
    doc_number: str
    doc_name: str
    phan: Optional[str] = None
    chuong: Optional[str] = None
    chuong_title: Optional[str] = None
    muc: Optional[str] = None
    dieu: Optional[str] = None
    dieu_title: Optional[str] = None
    chunk_index: int = 0


@dataclass
class Chunk:
    content: str
    metadata: DocumentMetadata
    

def read_txt(txt_path: str) -> str:
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        cleaned_content = remove_page_numbers(content)
        return cleaned_content.strip()
    except Exception as e:
        print(f"  Lỗi đọc TXT: {e}")
        return ""


def remove_page_numbers(text: str) -> str:
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.isdigit():
            continue
        if re.match(r'^[-–—\s]*\d+[-–—\s]*$', stripped):
            continue
        if re.match(r'^(Trang|Page|trang|page)\s*\d+$', stripped, re.IGNORECASE):
            continue
        if stripped.startswith('Formatted:'):
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def extract_doc_type(filename: str, content: str) -> str:
    filename_lower = filename.lower()
    content_lower = content[:2000].lower()
    
    if 'luat' in filename_lower or 'luật' in content_lower:
        return "Luật"
    elif 'nghi+dinh' in filename_lower or 'nghị định' in content_lower or 'nd-cp' in filename_lower.lower():
        return "Nghị định"
    elif 'thong+tu' in filename_lower or 'thông tư' in content_lower:
        return "Thông tư"
    elif 'quyet+dinh' in filename_lower or 'quyết định' in content_lower:
        return "Quyết định"
    else:
        return "Văn bản pháp luật"


def extract_doc_number(content: str) -> str:
    patterns = [
        r'(?:Luật|Nghị định|Thông tư|Quyết định)\s*số[:\s]*(\d+[\/\-]\d+[\/\-][\w\-]+)',
        r'số[:\s]*(\d+[\/\-]\d+[\/\-][\w\-]+)',
        r'(\d+\/\d{4}\/[\w\-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content[:3000], re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""


def extract_doc_name(content: str, filename: str) -> str:

    match = re.search(r'LUẬT\s*\n\s*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s]+)', content[:2000])
    if match:
        return "Luật " + match.group(1).strip().title()
    
    name = unquote(filename.replace('+', ' '))
    name = re.sub(r'^\d+\.\d*\.?\s*', '', name)
    name = re.sub(r'\.pdf$', '', name, flags=re.IGNORECASE)
    return name


def chunk_by_dieu(content: str, base_metadata: DocumentMetadata) -> List[Chunk]:
    chunks = []
    
    separator = r"Điều \d"
    
    text_splitter = RecursiveCharacterTextSplitter(
        separators=[separator, "\n\n", "\n", ". ", " "],
        is_separator_regex=True,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        keep_separator=True,
    )
    
    split_texts = text_splitter.split_text(content)
    
    current_phan = None
    current_chuong = None
    current_chuong_title = None
    current_muc = None
    
    for idx, text in enumerate(split_texts):
        if not text.strip():
            continue
        
        phan_match = re.search(r'(PHẦN THỨ\s+\w+)', text, re.IGNORECASE)
        if phan_match:
            current_phan = phan_match.group(1)
        
        chuong_match = re.search(r'(Chương\s+[IVXLC]+)\s*\n\s*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s,]+)', text)
        if chuong_match:
            current_chuong = chuong_match.group(1)
            current_chuong_title = chuong_match.group(2).strip()
        
        muc_match = re.search(r'(Mục\s+\d+)', text, re.IGNORECASE)
        if muc_match:
            current_muc = muc_match.group(1)
        
        dieu_match = re.match(r'(Điều\s+\d+[a-z]?)\.?\s*([^\n]*)', text)
        dieu_num = None
        dieu_title = None
        if dieu_match:
            dieu_num = dieu_match.group(1)
            dieu_title = dieu_match.group(2).strip() if dieu_match.group(2) else None
        
        metadata = DocumentMetadata(
            title=base_metadata.title,
            doc_type=base_metadata.doc_type,
            doc_number=base_metadata.doc_number,
            doc_name=base_metadata.doc_name,
            phan=current_phan,
            chuong=current_chuong,
            chuong_title=current_chuong_title,
            muc=current_muc,
            dieu=dieu_num,
            dieu_title=dieu_title,
            chunk_index=idx
        )
        chunks.append(Chunk(content=text.strip(), metadata=metadata))
    
    return chunks


class EmbeddingModel:
    def __init__(self, model_path: str):
        print(f"Loading embedding model from {model_path}...")
        self.model = SentenceTransformer(model_path)
        print(f"Model loaded. Vector size: {self.model.get_sentence_embedding_dimension()}")
    
    def encode(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts, show_progress_bar=True)
        return embeddings.tolist()
    
    def get_dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()


class QdrantStorage:
    def __init__(self, url: str, collection_name: str, vector_size: int):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._ensure_collection()
    
    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            print(f"Creating collection '{self.collection_name}'...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )
            print(f"Collection created with vector size {self.vector_size}")
        else:
            print(f"Collection '{self.collection_name}' already exists")
    
    def upsert(self, chunks: List[Chunk], embeddings: List[List[float]], start_id: int = 0):
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point = PointStruct(
                id=start_id + i,
                vector=embedding,
                payload={
                    "content": chunk.content,
                    **asdict(chunk.metadata)
                }
            )
            points.append(point)
        
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            print(f"  Upserted {min(i+batch_size, len(points))}/{len(points)} points")
        
        return len(points)


def process_txt(txt_path: str, embedding_model: EmbeddingModel) -> List[Dict]:
    filename = Path(txt_path).name
    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    
    content = read_txt(txt_path)
    if not content:
        print("  Không đọc được nội dung!")
        return []
    print(f"  Đọc được {len(content)} characters")
    
    base_metadata = DocumentMetadata(
        title=filename,
        doc_type=extract_doc_type(filename, content),
        doc_number=extract_doc_number(content),
        doc_name=extract_doc_name(content, filename)
    )
    print(f"  Loại: {base_metadata.doc_type}")
    print(f"  Số hiệu: {base_metadata.doc_number}")
    print(f"  Tên: {base_metadata.doc_name}")
    
    chunks = chunk_by_dieu(content, base_metadata)
    print(f"  Tạo được {len(chunks)} chunks")
    
    if not chunks:
        print("  Không tìm thấy cấu trúc Điều, dùng chunking đơn giản...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        texts = text_splitter.split_text(content)
        chunks = [
            Chunk(content=text, metadata=DocumentMetadata(
                title=filename,
                doc_type=base_metadata.doc_type,
                doc_number=base_metadata.doc_number,
                doc_name=base_metadata.doc_name,
                chunk_index=i
            ))
            for i, text in enumerate(texts)
        ]
        print(f"  Tạo được {len(chunks)} chunks (fallback)")
    
    print("  Đang tạo embeddings...")
    texts = [chunk.content for chunk in chunks]
    embeddings = embedding_model.encode(texts)
    
    results = []
    for chunk, embedding in zip(chunks, embeddings):
        results.append({
            "content": chunk.content,
            "metadata": asdict(chunk.metadata),
            "embedding": embedding
        })
    
    return results


def main():
    print("="*60)
    print("LEGAL DOCUMENT CHUNKING PIPELINE")
    print("="*60)
    
    txt_folder = Path(TXT_FOLDER)
    if not txt_folder.exists():
        txt_folder = Path(".")  # Current directory
    
    txt_files = list(txt_folder.glob("*.txt"))
    if not txt_files:
        print(f"Không tìm thấy file TXT trong {txt_folder}")
        return
    
    print(f"Tìm thấy {len(txt_files)} file TXT")
    
    model_path = Path(EMBEDDING_MODEL_PATH)
    if not model_path.exists():
        model_path = Path("data/models/vietnamese_embedding")
    
    embedding_model = EmbeddingModel(str(model_path))
    vector_size = embedding_model.get_dimension()
    
    all_results = []
    for txt_file in txt_files:
        results = process_txt(str(txt_file), embedding_model)
        all_results.extend(results)
    
    print(f"\n{'='*60}")
    print(f"TỔNG KẾT: Đã tạo {len(all_results)} chunks từ {len(txt_files)} files")
    
    print(f"\nExporting to {OUTPUT_JSON}...")
    json_data = []
    for r in all_results:
        json_data.append({
            "content": r["content"],
            "metadata": r["metadata"]
        })
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(json_data)} chunks to {OUTPUT_JSON}")
    
    print(f"\n{'='*60}")
    user_input = input(f"Upload lên Qdrant ({QDRANT_URL})? [y/N]: ").strip().lower()
    
    if user_input == 'y':
        print("\nConnecting to Qdrant...")
        storage = QdrantStorage(QDRANT_URL, COLLECTION_NAME, vector_size)
        
        chunks = [Chunk(content=r["content"], metadata=DocumentMetadata(**r["metadata"])) 
                  for r in all_results]
        embeddings = [r["embedding"] for r in all_results]
        
        print("Uploading to Qdrant...")
        count = storage.upsert(chunks, embeddings)
        print(f"Successfully uploaded {count} vectors to Qdrant!")
    else:
        print("Skipping Qdrant upload. Bạn có thể chạy lại script sau.")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
