# Benchmarks (ViLeXa-style)

Module benchmark retrieval cho project hiện tại, dùng format dữ liệu giống ViLeXa/Zalo:

- `queries.jsonl`
- `qrels/test.jsonl` (hoặc `qrels/train.jsonl`)

## Cài đặt dữ liệu

Thư mục dữ liệu cần có cấu trúc:

```text
data/your_benchmark/
├── queries.jsonl
└── qrels/
    └── test.jsonl
```

`queries.jsonl`:

```json
{"_id":"q1","text":"..."}
```

`qrels/test.jsonl`:

```json
{"query-id":"q1","corpus-id":"<chunk_id_or_vchunk_id>","score":1}
```

Lưu ý quan trọng:
- Mode `legal` so khớp với `chunk_id` (từ retriever legal).
- Mode `verdict` so khớp với `vchunk_id` (từ retriever verdict).

## Tạo internal benchmark từ collection `legal_chunks`

Khi muốn benchmark sát production hơn trên chính dữ liệu đã ingest trong hệ thống, tạo dataset nội bộ trực tiếp từ Qdrant collection `legal_chunks`:

```bash
python benchmarks/build_internal_legal_benchmark.py \
  --collection legal_chunks \
  --output-dir data/internal_legal_benchmark \
  --max-queries 1000 \
  --style mixed
```

Dataset sinh ra sẽ có:
- `data/internal_legal_benchmark/queries.jsonl`
- `data/internal_legal_benchmark/qrels/test.jsonl`

Chạy eval trên collection production legal:

```bash
python benchmarks/run_eval.py \
  --mode legal \
  --data-dir data/internal_legal_benchmark \
  --collection legal_chunks \
  --per-query
```

Ghi chú:
- Script tạo qrels theo format `doc_number+dieu` để khớp với mapping trong `benchmarks/pipeline_adapter.py`.
- Đây là internal benchmark auto-generated từ metadata hiện có, phù hợp để theo dõi regression và readiness nội bộ.

Nếu bạn dùng bộ Zalo/HuggingFace nhưng index hiện tại của project không chứa đúng các tài liệu/điều luật trong qrels, kết quả sẽ về 0 toàn bộ. Khi đó cần:
- Hoặc ingest đúng corpus tương ứng với qrels vào index benchmark riêng.
- Hoặc tạo bộ qrels nội bộ theo corpus hiện tại của bạn.

## Chạy benchmark

### Bước 0: Ingest corpus Zalo vào index benchmark riêng (đúng pipeline)

Lệnh này sẽ ingest đồng thời vào:
- Qdrant collection benchmark (mặc định: `bench_zalo_legal`)
- Neo4j `Document/Chunk` để retriever pipeline của bạn filter được candidate IDs

```bash
conda run -n shtt python -m benchmarks.ingest_zalo_legal_pipeline \
  --data-dir data/zalo_ai_retrieval \
  --split test \
  --collection bench_zalo_legal \
  --recreate
```

Legal:

```bash
python -m benchmarks.run_eval \
  --mode legal \
  --data-dir data/your_benchmark \
  --k-values 1,3,5,10,20 \
  --collection bench_zalo_legal
```

Verdict:

```bash
python -m benchmarks.run_eval \
  --mode verdict \
  --data-dir data/your_benchmark \
  --k-values 1,3,5,10,20
```

Lưu ý: script ingest ở trên hiện dành cho legal benchmark. Verdict benchmark cần bộ corpus/qrels và script ingest tương ứng cho `vchunk_id`.

Thêm filter (tùy chọn):

```bash
python -m benchmarks.run_eval \
  --mode legal \
  --data-dir data/your_benchmark \
  --query-date 2024-01-01 \
  --doc-types "Luat,Nghi dinh"
```

## Kết quả

Mặc định lưu tại `benchmarks/results/*.json`.
Các chỉ số hiện có:
- Precision@k
- Recall@k
- MRR
