import os
import json
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, asdict, field

from sentence_transformers import SentenceTransformer
import torch

from verdict_extractors import (
    clean_ocr_artifacts,
    extract_case_number, extract_case_number_from_filename,
    extract_court_name, extract_judgment_date,
    extract_dispute_type, extract_trial_level,
    extract_parties, extract_judges,
    detect_ip_types, extract_law_references,
    generate_summary,
)
from verdict_sections import (
    macro_chunk,
    micro_chunk_noi_dung,
    micro_chunk_nhan_dinh,
    micro_chunk_quyet_dinh,
)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

EMBEDDING_MODEL_PATH = str(Path(__file__).resolve().parent.parent.parent / "data" / "models" / "vietnamese_embedding")
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
TXT_FOLDER = os.path.join(_PROJECT_DIR, "output-ban-an")
OUTPUT_JSON = os.path.join(_SCRIPT_DIR, "verdict_chunks.json")
OUTPUT_WITH_EMBEDDINGS = os.path.join(_SCRIPT_DIR, "verdict_chunks_with_embeddings.json")


@dataclass
class VerdictMetadata:
    filename: str
    case_number: str = ""
    court_name: str = ""
    judgment_date: str = ""
    dispute_type: str = ""
    trial_level: str = ""
    plaintiff: str = ""
    defendant: str = ""
    third_party: str = ""
    ip_types: List[str] = field(default_factory=list)
    judges: str = ""
    law_references: List[str] = field(default_factory=list)
    summary: str = ""
    chunk_index: int = 0
    section_type: str = "header"
    party_role: str = ""
    point_number: str = ""
    item_number: str = ""


@dataclass
class VerdictChunk:
    content: str
    metadata: VerdictMetadata


def _extract_all_metadata(text: str, filename: str) -> dict:
    case_number = extract_case_number(text) or extract_case_number_from_filename(filename)
    plaintiff, defendant, third_party = extract_parties(text)

    meta = {
        'filename': filename,
        'case_number': case_number,
        'court_name': extract_court_name(text),
        'judgment_date': extract_judgment_date(text),
        'dispute_type': extract_dispute_type(text),
        'trial_level': extract_trial_level(text, case_number),
        'plaintiff': plaintiff,
        'defendant': defendant,
        'third_party': third_party,
        'ip_types': detect_ip_types(text),
        'judges': extract_judges(text),
        'law_references': extract_law_references(text),
    }
    meta['summary'] = generate_summary(meta)
    return meta


def chunk_verdict(filepath: str) -> List[VerdictChunk]:
    filename = Path(filepath).name
    print(f"\n📄 Processing: {filename}")

    with open(filepath, 'r', encoding='utf-8') as f:
        text = clean_ocr_artifacts(f.read())

    base_meta = _extract_all_metadata(text, filename)
    sections = macro_chunk(text)
    chunks = []
    chunk_idx = 0

    if sections['header']:
        meta = VerdictMetadata(**base_meta, chunk_index=chunk_idx, section_type='header')
        chunks.append(VerdictChunk(content=sections['header'], metadata=meta))
        chunk_idx += 1

    for content, party_role in micro_chunk_noi_dung(sections['noi_dung']):
        section_type = 'lower_court_decision' if party_role == 'bản án sơ thẩm' else 'fact'
        meta = VerdictMetadata(**base_meta, chunk_index=chunk_idx, section_type=section_type, party_role=party_role)
        chunks.append(VerdictChunk(content=content, metadata=meta))
        chunk_idx += 1

    for content, point_number in micro_chunk_nhan_dinh(sections['nhan_dinh']):
        meta = VerdictMetadata(**base_meta, chunk_index=chunk_idx, section_type='reasoning', point_number=point_number)
        chunks.append(VerdictChunk(content=content, metadata=meta))
        chunk_idx += 1

    for content, item_number in micro_chunk_quyet_dinh(sections['quyet_dinh']):
        is_court_fee = 'án phí' in item_number.lower()
        section_type = 'court_fee' if is_court_fee else 'decision_item'
        clean_item = item_number.replace('án phí ', '') if is_court_fee else item_number
        meta = VerdictMetadata(**base_meta, chunk_index=chunk_idx, section_type=section_type, item_number=clean_item)
        chunks.append(VerdictChunk(content=content, metadata=meta))
        chunk_idx += 1

    print(f"   ✓ {len(chunks)} chunks | {base_meta['case_number']} | {', '.join(base_meta['ip_types'])}")
    return chunks


def chunk_all_verdicts(folder: str) -> List[VerdictChunk]:
    txt_files = sorted(Path(folder).glob("*.txt"))
    print(f"⚖️  VERDICT CHUNKER — {len(txt_files)} files in {folder}")

    all_chunks = []
    for filepath in txt_files:
        try:
            all_chunks.extend(chunk_verdict(str(filepath)))
        except Exception as e:
            print(f"   ❌ Error: {filepath.name}: {e}")

    print(f"\n📊 Total: {len(all_chunks)} chunks from {len(txt_files)} files")
    return all_chunks


def generate_embeddings(chunks: List[VerdictChunk]) -> List[Dict]:
    print(f"\n🔢 Generating embeddings on {DEVICE}...")
    model = SentenceTransformer(EMBEDDING_MODEL_PATH, device=DEVICE)
    texts = [c.content for c in chunks]
    batch_size = 32
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        embeddings = model.encode(texts[i:i + batch_size], show_progress_bar=False, normalize_embeddings=True)
        all_embeddings.extend(embeddings.tolist())
        print(f"   {min(i + batch_size, len(texts))}/{len(texts)}")

    return [
        {'content': c.content, 'metadata': asdict(c.metadata), 'embedding': emb}
        for c, emb in zip(chunks, all_embeddings)
    ]


def export_json(chunks: List[VerdictChunk], path: str):
    data = [{'content': c.content, 'metadata': asdict(c.metadata)} for c in chunks]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 Exported {len(data)} chunks → {path}")


def export_with_embeddings(data: List[Dict], path: str):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    size_mb = Path(path).stat().st_size / (1024 * 1024)
    print(f"💾 Exported {len(data)} chunks with embeddings → {path} ({size_mb:.1f} MB)")


def main():
    chunks = chunk_all_verdicts(TXT_FOLDER)
    if not chunks:
        print("❌ No chunks generated!")
        return

    export_json(chunks, OUTPUT_JSON)
    data = generate_embeddings(chunks)
    export_with_embeddings(data, OUTPUT_WITH_EMBEDDINGS)
    print("✅ Done!")


if __name__ == "__main__":
    main()
