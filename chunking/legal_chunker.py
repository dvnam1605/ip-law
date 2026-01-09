import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from urllib.parse import unquote

# Embedding
from sentence_transformers import SentenceTransformer

# Vector DB
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# LangChain text splitting
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ============ CONFIGURATION ============
QDRANT_URL = "http://192.168.1.199:6333"
COLLECTION_NAME = "Luật sở hữu trí tuệ"
EMBEDDING_MODEL_PATH = "./vietnamese_embedding"
VECTOR_SIZE = 1024  # Adjust based on your model

# Chunking config
CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

# Paths
TXT_FOLDER = "./output"
OUTPUT_JSON = "./chunks_output.json"


# ============ DATA CLASSES ============
@dataclass
class DocumentMetadata:
    """Metadata cho mỗi văn bản pháp luật"""
    title: str  # Tên file nguồn
    doc_type: str  # Loại văn bản: Luật, Nghị định, Thông tư
    doc_number: str  # Số hiệu: 23/2018/QH14
    doc_name: str  # Tên: Luật Cạnh tranh
    phan: Optional[str] = None  # Phần
    chuong: Optional[str] = None  # Chương
    chuong_title: Optional[str] = None  # Tiêu đề chương
    muc: Optional[str] = None  # Mục
    dieu: Optional[str] = None  # Điều
    dieu_title: Optional[str] = None  # Tiêu đề điều
    chunk_index: int = 0  # Thứ tự chunk trong điều


@dataclass
class Chunk:
    """Một chunk văn bản"""
    content: str
    metadata: DocumentMetadata
    

# ============ TXT READER ============
def read_txt(txt_path: str) -> str:
    """Đọc nội dung file TXT và loại bỏ số trang"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Loại bỏ số trang
        cleaned_content = remove_page_numbers(content)
        return cleaned_content.strip()
    except Exception as e:
        print(f"  Lỗi đọc TXT: {e}")
        return ""


def remove_page_numbers(text: str) -> str:
    """Loại bỏ số trang và các thông tin format không cần thiết"""
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Bỏ số trang đơn
        if stripped.isdigit():
            continue
        # Bỏ dạng "- 1 -" hoặc "— 2 —"
        if re.match(r'^[-–—\s]*\d+[-–—\s]*$', stripped):
            continue
        # Bỏ "Trang X", "Page X"
        if re.match(r'^(Trang|Page|trang|page)\s*\d+$', stripped, re.IGNORECASE):
            continue
        # Bỏ thông tin format Word (Formatted: ...)
        if stripped.startswith('Formatted:'):
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


# ============ METADATA EXTRACTION ============
def extract_doc_type(filename: str, content: str) -> str:
    """Xác định loại văn bản"""
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
    """Trích xuất số hiệu văn bản"""
    # Pattern: Luật số: 23/2018/QH14, Nghị định số 103/2006/NĐ-CP
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
    """Trích xuất tên văn bản"""
    # Tìm LUẬT\n<TÊN LUẬT>
    match = re.search(r'LUẬT\s*\n\s*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s]+)', content[:2000])
    if match:
        return "Luật " + match.group(1).strip().title()
    
    # Fallback: dùng tên file
    name = unquote(filename.replace('+', ' '))
    # Loại bỏ prefix số và extension
    name = re.sub(r'^\d+\.\d*\.?\s*', '', name)
    name = re.sub(r'\.pdf$', '', name, flags=re.IGNORECASE)
    return name


# ============ CHUNKING BY ĐIỀU ============
def chunk_by_dieu(content: str, base_metadata: DocumentMetadata) -> List[Chunk]:
    """
    Chunk văn bản theo Điều sử dụng RecursiveCharacterTextSplitter
    Separator chính là "Điều " để đảm bảo mỗi chunk bắt đầu từ một Điều
    """
    chunks = []
    
    # Separator chính là "Điều + số" - pattern phổ biến trong văn bản luật
    separator = r"Điều \d"
    
    # Initialize RecursiveCharacterTextSplitter với Điều làm separator chính
    text_splitter = RecursiveCharacterTextSplitter(
        separators=[separator, "\n\n", "\n", ". ", " "],  # Ưu tiên split theo Điều + số
        is_separator_regex=True,  # Bật chế độ regex cho separator
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        keep_separator=True,  # Giữ lại "Điều " trong chunk
    )
    
    # Split toàn bộ content
    split_texts = text_splitter.split_text(content)
    
    # Track current context (Phần, Chương, Mục) khi duyệt qua text
    current_phan = None
    current_chuong = None
    current_chuong_title = None
    current_muc = None
    
    for idx, text in enumerate(split_texts):
        if not text.strip():
            continue
        
        # Cập nhật context từ headers trong text
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
        
        # Trích xuất Điều và tiêu đề từ chunk
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


# ============ EMBEDDING ============
class EmbeddingModel:
    def __init__(self, model_path: str):
        print(f"Loading embedding model from {model_path}...")
        self.model = SentenceTransformer(model_path)
        print(f"Model loaded. Vector size: {self.model.get_sentence_embedding_dimension()}")
    
    def encode(self, texts: List[str]) -> List[List[float]]:
        """Tạo embeddings cho danh sách texts"""
        embeddings = self.model.encode(texts, show_progress_bar=True)
        return embeddings.tolist()
    
    def get_dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()


# ============ QDRANT ============
class QdrantStorage:
    def __init__(self, url: str, collection_name: str, vector_size: int):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Tạo collection nếu chưa tồn tại"""
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
        """Lưu chunks vào Qdrant"""
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
        
        # Upsert theo batch
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            print(f"  Upserted {min(i+batch_size, len(points))}/{len(points)} points")
        
        return len(points)


# ============ MAIN PIPELINE ============
def process_txt(txt_path: str, embedding_model: EmbeddingModel) -> List[Dict]:
    """Xử lý một file TXT và trả về chunks với embeddings"""
    filename = Path(txt_path).name
    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    
    # 1. Đọc TXT
    content = read_txt(txt_path)
    if not content:
        print("  Không đọc được nội dung!")
        return []
    print(f"  Đọc được {len(content)} characters")
    
    # 2. Trích xuất metadata cơ bản
    base_metadata = DocumentMetadata(
        title=filename,
        doc_type=extract_doc_type(filename, content),
        doc_number=extract_doc_number(content),
        doc_name=extract_doc_name(content, filename)
    )
    print(f"  Loại: {base_metadata.doc_type}")
    print(f"  Số hiệu: {base_metadata.doc_number}")
    print(f"  Tên: {base_metadata.doc_name}")
    
    # 3. Chunk theo Điều
    chunks = chunk_by_dieu(content, base_metadata)
    print(f"  Tạo được {len(chunks)} chunks")
    
    if not chunks:
        # Fallback: chunk đơn giản nếu không tìm thấy Điều
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
    
    # 4. Tạo embeddings
    print("  Đang tạo embeddings...")
    texts = [chunk.content for chunk in chunks]
    embeddings = embedding_model.encode(texts)
    
    # 5. Trả về kết quả
    results = []
    for chunk, embedding in zip(chunks, embeddings):
        results.append({
            "content": chunk.content,
            "metadata": asdict(chunk.metadata),
            "embedding": embedding
        })
    
    return results


def main():
    """Main entry point"""
    print("="*60)
    print("LEGAL DOCUMENT CHUNKING PIPELINE")
    print("="*60)
    
    # Paths
    txt_folder = Path(TXT_FOLDER)
    if not txt_folder.exists():
        txt_folder = Path(".")  # Current directory
    
    # Tìm tất cả TXT
    txt_files = list(txt_folder.glob("*.txt"))
    if not txt_files:
        print(f"Không tìm thấy file TXT trong {txt_folder}")
        return
    
    print(f"Tìm thấy {len(txt_files)} file TXT")
    
    # Load embedding model
    model_path = Path(EMBEDDING_MODEL_PATH)
    if not model_path.exists():
        model_path = Path("vietnamese_embedding")
    
    embedding_model = EmbeddingModel(str(model_path))
    vector_size = embedding_model.get_dimension()
    
    # Xử lý từng TXT
    all_results = []
    for txt_file in txt_files:
        results = process_txt(str(txt_file), embedding_model)
        all_results.extend(results)
    
    print(f"\n{'='*60}")
    print(f"TỔNG KẾT: Đã tạo {len(all_results)} chunks từ {len(txt_files)} files")
    
    # Export to JSON (không bao gồm embeddings để file nhỏ hơn)
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
    
    # Hỏi user có muốn upload lên Qdrant không
    print(f"\n{'='*60}")
    user_input = input(f"Upload lên Qdrant ({QDRANT_URL})? [y/N]: ").strip().lower()
    
    if user_input == 'y':
        print("\nConnecting to Qdrant...")
        storage = QdrantStorage(QDRANT_URL, COLLECTION_NAME, vector_size)
        
        # Extract chunks và embeddings
        chunks = [Chunk(content=r["content"], metadata=DocumentMetadata(**r["metadata"])) 
                  for r in all_results]
        embeddings = [r["embedding"] for r in all_results]
        
        # Upload
        print("Uploading to Qdrant...")
        count = storage.upsert(chunks, embeddings)
        print(f"Successfully uploaded {count} vectors to Qdrant!")
    else:
        print("Skipping Qdrant upload. Bạn có thể chạy lại script sau.")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
