import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from urllib.parse import unquote
from datetime import datetime, timedelta

from sentence_transformers import SentenceTransformer
import torch

from langchain_text_splitters import RecursiveCharacterTextSplitter


os.environ["CUDA_VISIBLE_DEVICES"] = "1"
CUDA_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

EMBEDDING_MODEL_PATH = "./vietnamese_embedding"
VECTOR_SIZE = 1024

CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

TXT_FOLDER = "./output"
OUTPUT_JSON = "./chunks_output_v2.json"
OUTPUT_WITH_EMBEDDINGS = "./chunks_output_v2_with_embeddings.json"
EFFECTIVE_DATES_JSON = "./effective_dates.json"


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
    
    # Fallback to content header
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
    
    # Pattern 2: "có hiệu lực kể từ ngày ký"
    if re.search(r'có\s+hiệu\s+lực.*?kể\s+từ\s+ngày\s+ký', content, re.IGNORECASE):
        return signing_date
    
    # Pattern 3: "có hiệu lực sau X ngày"
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
    """Returns: (dieu, dieu_title, is_continuation)"""
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
    
    match = re.search(r'^["\']?(Điều\s+\d+[a-z]?)\.?\s*([^"\'\n]*)["\']?', text_stripped[:500])
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
    """Returns: 'header' | 'content' | 'appendix' | 'signature'"""
    text_upper = text[:800].upper()
    text_lower = text[:800].lower()
    
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


def chunk_by_dieu_v2(content: str, base_metadata: DocumentMetadata) -> List[Chunk]:
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
        print(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"GPU: {torch.cuda.get_device_name(0)}")
        
        self.model = SentenceTransformer(model_path, device=self.device)
        print(f"Model loaded. Vector size: {self.model.get_sentence_embedding_dimension()}")
    
    def encode(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        embeddings = self.model.encode(
            texts, 
            show_progress_bar=True,
            batch_size=batch_size,
            device=self.device
        )
        return embeddings.tolist()
    
    def get_dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()


def process_txt_v2(txt_path: str, embedding_model: EmbeddingModel) -> List[Dict]:
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
    
    chunks = chunk_by_dieu_v2(content, base_metadata)
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
                chunk_index=i,
                chunk_type="content"
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


def analyze_chunks(chunks_data: List[Dict]) -> Dict:
    total = len(chunks_data)
    stats = {
        'total': total,
        'null_counts': {},
        'chunk_types': {},
        'by_doc_type': {}
    }
    
    for chunk in chunks_data:
        meta = chunk.get('metadata', {})
        # Count nulls
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


def main():
    print("="*60)
    print("LEGAL DOCUMENT CHUNKING PIPELINE V2")
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
        model_path = Path("vietnamese_embedding")
    
    embedding_model = EmbeddingModel(str(model_path))
    vector_size = embedding_model.get_dimension()
    
    all_results = []
    for txt_file in txt_files:
        results = process_txt_v2(str(txt_file), embedding_model)
        all_results.extend(results)
    
    print(f"\n{'='*60}")
    print(f"TỔNG KẾT: Đã tạo {len(all_results)} chunks từ {len(txt_files)} files")
    
    stats = analyze_chunks(all_results)
    print_analysis(stats)
    
    print(f"\nExporting to {OUTPUT_JSON}...")
    json_data = []
    for r in all_results:
        json_data.append({
            "content": r["content"],
            "metadata": r["metadata"]
        })
    
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(json_data)} chunks (metadata only) to {OUTPUT_JSON}")
    
    embeddings_file = OUTPUT_JSON.replace('.json', '_with_embeddings.json')
    print(f"\nExporting with embeddings to {embeddings_file}...")
    with open(embeddings_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False)
    print(f"Exported {len(all_results)} chunks with embeddings to {embeddings_file}")
    
    print(f"\n{'='*60}")
    print("Next steps:")
    print(f"  1. Review chunks in: {OUTPUT_JSON}")
    print(f"  2. Run neo4j_ingest.py to import into Neo4j:")
    print(f"     python neo4j_ingest.py --input {embeddings_file}")
    print("\nDone!")


if __name__ == "__main__":
    main()
