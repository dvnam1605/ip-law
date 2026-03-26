import os
import re
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import unquote
from datetime import datetime, timedelta

from sentence_transformers import SentenceTransformer
import torch

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from langchain_text_splitters import RecursiveCharacterTextSplitter


os.environ["CUDA_VISIBLE_DEVICES"] = "0"
CUDA_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

QDRANT_URL = os.getenv("QDRANT_URL", "http://192.168.1.199:6333")
LEGAL_COLLECTION = os.getenv("QDRANT_LEGAL_COLLECTION", "legal_chunks")
EMBEDDING_MODEL_PATH = "/home/namdv/shtt/data/models/vietnamese_embedding"
VECTOR_SIZE = 1024

CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

TXT_FOLDER = "/home/namdv/shtt/data/processed/phap-luat"
OUTPUT_JSON = "./chunks_output_v2.json"



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

    chunk_type: str = "content"
    effective_date: Optional[str] = None
    issuing_agency: Optional[str] = None
    signing_date: Optional[str] = None
    status: str = "active"
    is_continuation: bool = False


@dataclass
class Chunk:
    content: str
    metadata: DocumentMetadata

def generate_chunk_id(content: str, doc_id: str, chunk_index: int) -> str:
    hash_input = f"{doc_id}_{chunk_index}_{content[:100]}"
    return hashlib.md5(hash_input.encode()).hexdigest()[:16]


def read_txt(txt_path: str) -> str:
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return remove_page_numbers(content).strip()
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
    content_header = content[:500].lower()

    if 'thong+tu' in filename_lower or 'thông+tư' in filename_lower:
        if 'lien+tich' in filename_lower or 'liên+tịch' in filename_lower:
            return "Thông tư liên tịch"
        return "Thông tư"
    elif 'nghi+dinh' in filename_lower or 'nghị+định' in filename_lower or 'nd-cp' in filename_lower:
        return "Nghị định"
    elif 'quyet+dinh' in filename_lower or 'quyết+định' in filename_lower:
        return "Quyết định"
    elif 'bo+luat' in filename_lower or 'bộ+luật' in filename_lower:
        return "Bộ luật"
    elif 'luat' in filename_lower:
        return "Luật"

    if 'thông tư liên tịch' in content_header:
        return "Thông tư liên tịch"
    elif 'thông tư' in content_header:
        return "Thông tư"
    elif 'nghị định' in content_header:
        return "Nghị định"
    elif 'bộ luật' in content_header:
        return "Bộ luật"
    elif 'luật' in content_header:
        return "Luật"
    elif 'quyết định' in content_header:
        return "Quyết định"

    return "Văn bản pháp luật"


def extract_doc_number(content: str) -> str:
    patterns = [
        r'(?:Luật|Nghị định|Thông tư|Quyết định|Bộ luật)\s*số[:\s]*(\d+[\/\-]\d+[\/\-][\w\-]+)',
        r'Số[:\s]*(\d+[\/\-]\d+[\/\-][\w\-]+)',
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

    match = re.search(r'BỘ LUẬT\s*\n\s*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s]+)', content[:2000])
    if match:
        return "Bộ luật " + match.group(1).strip().title()

    name = unquote(filename.replace('+', ' '))
    name = re.sub(r'^\d+\.\d*\.?\s*', '', name)
    name = re.sub(r'\.txt$', '', name, flags=re.IGNORECASE)
    return name


def extract_issuing_agency(content: str) -> Optional[str]:
    header = content[:1000].upper()
    if 'QUỐC HỘI' in header:
        return "Quốc hội"
    elif 'CHÍNH PHỦ' in header:
        return "Chính phủ"
    elif 'BỘ KHOA HỌC VÀ CÔNG NGHỆ' in header:
        return "Bộ Khoa học và Công nghệ"
    elif 'BỘ TÀI CHÍNH' in header:
        return "Bộ Tài chính"
    elif 'BỘ NÔNG NGHIỆP' in header:
        return "Bộ Nông nghiệp và Phát triển nông thôn"
    elif 'BỘ VĂN HÓA' in header or 'BỘ VĂN HOÁ' in header:
        return "Bộ Văn hóa, Thể thao và Du lịch"
    elif 'BỘ CÔNG THƯƠNG' in header:
        return "Bộ Công Thương"
    elif 'BỘ ' in header:
        match = re.search(r'(BỘ\s+[A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s]+)', header)
        if match:
            return match.group(1).strip().title()
    return None


def extract_signing_date(content: str) -> Optional[str]:
    patterns = [
        r'ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})',
        r'(\d{1,2})/(\d{1,2})/(\d{4})',
    ]
    header = content[:2000]
    for pattern in patterns:
        match = re.search(pattern, header, re.IGNORECASE)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


def extract_effective_date(content: str, signing_date: Optional[str] = None) -> Optional[str]:
    match = re.search(
        r'có\s+hiệu\s+lực.*?(?:từ|kể từ)\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})',
        content, re.IGNORECASE
    )
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    if re.search(r'có\s+hiệu\s+lực.*?kể\s+từ\s+ngày\s+ký', content, re.IGNORECASE):
        return signing_date

    match = re.search(r'có\s+hiệu\s+lực.*?sau\s+(\d+)\s+ngày', content, re.IGNORECASE)
    if match and signing_date:
        try:
            days = int(match.group(1))
            sign_date = datetime.strptime(signing_date, "%Y-%m-%d")
            eff_date = sign_date + timedelta(days=days)
            return eff_date.strftime("%Y-%m-%d")
        except:
            pass

    return None


def extract_dieu_info(text: str, previous_dieu: Optional[str] = None,
                      previous_dieu_title: Optional[str] = None) -> Tuple[Optional[str], Optional[str], bool]:
    text_stripped = text.strip()

    match = re.match(r'(Điều\s+\d+[a-z]?)\.?\s*([^\n]*)', text_stripped)
    if match:
        dieu = match.group(1)
        title = match.group(2).strip() if match.group(2) else None
        if title and len(title) < 3:
            title = None
        return dieu, title, False

    match = re.search(r'(\d+)\.\s*(Điều\s+\d+[a-z]?)\s+được\s+sửa\s+đổi', text_stripped[:500])
    if match:
        return match.group(2), "sửa đổi, bổ sung", False

    match = re.search(r'^["\'"]?(Điều\s+\d+[a-z]?)\.?\s*([^"\'"\n]*)["\'"]?', text_stripped[:500])
    if match:
        return match.group(1), match.group(2).strip() or None, False

    match = re.search(r'(Điều\s+\d+[a-z]?)\.?\s*([^\n]{0,100})', text_stripped[:1000])
    if match:
        dieu = match.group(1)
        title = match.group(2).strip()
        if title and (len(title) < 3 or title.startswith('của') or title.startswith('và')):
            title = None
        return dieu, title, False

    if previous_dieu:
        starts_with_header = any(
            text_stripped.upper().startswith(h)
            for h in ['CHƯƠNG', 'PHẦN', 'MỤC', 'QUỐC HỘI', 'CHÍNH PHỦ', 'BỘ ']
        )
        if not starts_with_header:
            return previous_dieu, f"(tiếp theo {previous_dieu})", True

    return None, None, False


def detect_chunk_type(text: str, chunk_index: int, total_chunks: int) -> str:
    text_upper = text[:800].upper()

    if chunk_index == 0:
        return "header"

    header_keywords = [
        'QUỐC HỘI', 'CHÍNH PHỦ', 'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
        'ĐỘC LẬP - TỰ DO - HẠNH PHÚC', 'NƯỚC CỘNG HÒA'
    ]
    if chunk_index < 3 and any(kw in text_upper for kw in header_keywords):
        if not re.search(r'Điều\s+\d+', text):
            return "header"

    appendix_keywords = ['PHỤ LỤC', 'BIỂU MẪU', 'MẪU SỐ', 'DANH MỤC']
    if any(kw in text_upper for kw in appendix_keywords):
        return "appendix"

    if chunk_index >= total_chunks - 3:
        signature_patterns = [
            r'(TM\.|T\.M\.|THAY MẶT)',
            r'(CHỦ TỊCH|BỘ TRƯỞNG|THỦ TƯỚNG)',
            r'(Nơi nhận|NƠI NHẬN)',
        ]
        for pattern in signature_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "signature"

    return "content"



def chunk_by_dieu(content: str, base_metadata: DocumentMetadata) -> List[Chunk]:
    chunks = []

    signing_date = extract_signing_date(content)
    effective_date = extract_effective_date(content, signing_date)
    issuing_agency = extract_issuing_agency(content)

    separator = r"Điều \d"
    text_splitter = RecursiveCharacterTextSplitter(
        separators=[separator, "\n\n", "\n", ". ", " "],
        is_separator_regex=True,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        keep_separator=True,
    )

    split_texts = text_splitter.split_text(content)
    total_chunks = len(split_texts)

    current_phan = None
    current_chuong = None
    current_chuong_title = None
    current_muc = None
    previous_dieu = None
    previous_dieu_title = None

    for idx, text in enumerate(split_texts):
        if not text.strip():
            continue

        chunk_type = detect_chunk_type(text, idx, total_chunks)

        phan_match = re.search(r'(PHẦN THỨ\s+\w+)', text, re.IGNORECASE)
        if phan_match:
            current_phan = phan_match.group(1)

        chuong_patterns = [
            r'(Chương\s+[IVXLC]+)[:\s]*\n\s*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s,]+)',
            r'(CHƯƠNG\s+[IVXLC]+)[:\s]*\n\s*([A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ\s,]+)',
            r'(Chương\s+\d+)[:\s]*\n\s*([^\n]+)',
        ]
        for pattern in chuong_patterns:
            chuong_match = re.search(pattern, text)
            if chuong_match:
                current_chuong = chuong_match.group(1)
                current_chuong_title = chuong_match.group(2).strip()
                break

        muc_match = re.search(r'(Mục\s+\d+)', text, re.IGNORECASE)
        if muc_match:
            current_muc = muc_match.group(1)

        dieu_num, dieu_title, is_continuation = extract_dieu_info(
            text, previous_dieu, previous_dieu_title
        )

        if dieu_num and not is_continuation:
            previous_dieu = dieu_num
            previous_dieu_title = dieu_title

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
            chunk_index=idx,
            chunk_type=chunk_type,
            effective_date=effective_date,
            issuing_agency=issuing_agency,
            signing_date=signing_date,
            status="active",
            is_continuation=is_continuation
        )
        chunks.append(Chunk(content=text.strip(), metadata=metadata))

    return chunks



class EmbeddingModel:
    def __init__(self, model_path: str, device: str = None):
        self.device = device or CUDA_DEVICE
        print(f"Loading embedding model from {model_path}...")
        print(f"Using device: {self.device}")
        if torch.cuda.is_available():
            print(f"GPU: {torch.cuda.get_device_name(0)}")
        self.model = SentenceTransformer(model_path, device=self.device)
        print(f"Model loaded. Vector size: {self.model.get_sentence_embedding_dimension()}")

    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        embeddings = self.model.encode(
            texts, show_progress_bar=True,
            batch_size=batch_size, device=self.device
        )
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
            print(f"✓ Collection created (dim={self.vector_size})")
        else:
            print(f"⏭ Collection '{self.collection_name}' already exists")

    def upsert_results(self, results: List[Dict], start_id: int = 0):
        """Upsert chunking results directly to Qdrant."""
        points = []
        for i, r in enumerate(results):
            meta = r["metadata"]
            doc_id = meta.get("doc_number") or meta.get("title", "")
            chunk_id = generate_chunk_id(r["content"], doc_id, meta.get("chunk_index", 0))

            payload = {"chunk_id": chunk_id, **meta}
            point = PointStruct(
                id=start_id + i,
                vector=r["embedding"],
                payload=payload
            )
            points.append(point)

        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            print(f"  ✓ Uploaded {min(i+batch_size, len(points))}/{len(points)} points")

        return len(points)



def analyze_chunks(chunks_data: List[Dict]) -> Dict:
    total = len(chunks_data)
    stats = {'total': total, 'null_counts': {}, 'chunk_types': {}, 'by_doc_type': {}}
    for chunk in chunks_data:
        meta = chunk.get('metadata', {})
        for key, value in meta.items():
            if key not in stats['null_counts']:
                stats['null_counts'][key] = {'null': 0, 'not_null': 0}
            if value is None:
                stats['null_counts'][key]['null'] += 1
            else:
                stats['null_counts'][key]['not_null'] += 1
        chunk_type = meta.get('chunk_type', 'unknown')
        stats['chunk_types'][chunk_type] = stats['chunk_types'].get(chunk_type, 0) + 1
        doc_type = meta.get('doc_type', 'unknown')
        stats['by_doc_type'][doc_type] = stats['by_doc_type'].get(doc_type, 0) + 1
    return stats


def print_analysis(stats: Dict):
    print(f"\n{'='*60}")
    print("PHÂN TÍCH CHẤT LƯỢNG CHUNKS")
    print(f"{'='*60}")
    print(f"Total chunks: {stats['total']}")
    print("\n--- Null Analysis ---")
    for key, counts in sorted(stats['null_counts'].items()):
        null_pct = counts['null'] / stats['total'] * 100
        status = "✅" if null_pct < 10 else ("⚠️" if null_pct < 30 else "🔴")
        print(f"{status} {key:18} | null: {counts['null']:4} ({null_pct:5.1f}%) | not_null: {counts['not_null']:4}")
    print("\n--- Chunk Types ---")
    for ctype, count in sorted(stats['chunk_types'].items()):
        print(f"  {ctype:15} : {count:4} ({count/stats['total']*100:5.1f}%)")
    print("\n--- By Document Type ---")
    for dtype, count in sorted(stats['by_doc_type'].items()):
        print(f"  {dtype:20} : {count:4}")



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
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        )
        texts = text_splitter.split_text(content)
        chunks = [
            Chunk(content=text, metadata=DocumentMetadata(
                title=filename,
                doc_type=base_metadata.doc_type,
                doc_number=base_metadata.doc_number,
                doc_name=base_metadata.doc_name,
                chunk_index=i, chunk_type="content"
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
        txt_folder = Path(".")

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

    stats = analyze_chunks(all_results)
    print_analysis(stats)

    # Save metadata-only JSON (for Neo4j ingest)
    print(f"\nExporting metadata to {OUTPUT_JSON}...")
    json_data = [{"content": r["content"], "metadata": r["metadata"]} for r in all_results]
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"✓ Exported {len(json_data)} chunks → {OUTPUT_JSON}")

    # Upload to Qdrant directly
    print(f"\n🔄 Uploading to Qdrant ({QDRANT_URL})...")
    storage = QdrantStorage(QDRANT_URL, LEGAL_COLLECTION, vector_size)
    count = storage.upsert_results(all_results)
    print(f"✅ Uploaded {count} vectors to Qdrant collection '{LEGAL_COLLECTION}'")

    print("\nDone!")


if __name__ == "__main__":
    main()
