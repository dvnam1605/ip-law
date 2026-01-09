import json
import random
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load Qwen2.5 model
print("Loading Qwen2.5 model...")
model_name = "Qwen/Qwen2.5-3B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    device_map="auto"
)
print("Model loaded successfully!")

# Question types for diversity
QUESTION_TYPES = [
    "factoid - Hỏi về thông tin cụ thể, số liệu, định nghĩa",
    "giải thích - Yêu cầu giải thích khái niệm, hiện tượng",
    "so sánh - So sánh giữa các khái niệm, phương pháp",
    "quy trình - Hỏi về các bước, trình tự thực hiện",
    "truy vấn tri thức - Hỏi về mối quan hệ, nguyên nhân, kết quả",
    "tổng hợp - Câu hỏi cần tổng hợp thông tin từ nhiều nguồn"
]

def load_chunks(file_path):
    """Load all chunks from JSONL file"""
    chunks = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks

def generate_question(chunks_content, question_type):
    """Generate a natural question using Qwen2.5"""
    
    # Combine chunks content
    combined_content = "\n\n".join([chunk['text'] for chunk in chunks_content])
    
    # Limit content length to avoid token limit
    if len(combined_content) > 2000:
        combined_content = combined_content[:2000] + "..."
    
    prompt = f"""Bạn là chuyên gia sinh câu hỏi tự nhiên cho hệ thống RAG.

Dựa trên nội dung sau:
{combined_content}

Hãy sinh 1 câu hỏi kiểu "{question_type}" mà:
- Người dùng thật thường hỏi
- Tự nhiên, không lộ thông tin chunk gốc
- Có thể trả lời được từ nội dung đã cho
- Phù hợp ngữ cảnh tiếng Việt

CHỈ TRẢ VỀ CÂU HỎI, KHÔNG GIẢI THÍCH THÊM."""

    try:
        messages = [
            {"role": "system", "content": "Bạn là chuyên gia sinh câu hỏi cho hệ thống RAG. Chỉ trả về câu hỏi, không giải thích."},
            {"role": "user", "content": prompt}
        ]
        
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        model_inputs = tokenizer([text], return_tensors="pt").to(model.device)
        
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=150,
            temperature=0.7,
            top_p=0.9,
            do_sample=True
        )
        
        generated_ids = [
            output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        
        response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        question = response.strip()
        
        # Clean up the question
        question = question.strip('"').strip("'").strip()
        
        # Remove common prefixes
        prefixes_to_remove = ["Câu hỏi:", "Question:", "Hỏi:"]
        for prefix in prefixes_to_remove:
            if question.startswith(prefix):
                question = question[len(prefix):].strip()
        
        return question
    except Exception as e:
        print(f"Error generating question: {e}")
        return None

def create_evaluation_sample(all_chunks, used_questions):
    """Create one evaluation sample"""
    
    # Randomly select 1-3 chunks
    num_chunks = random.randint(1, 3)
    selected_chunks = random.sample(all_chunks, num_chunks)
    
    # Randomly select question type
    question_type = random.choice(QUESTION_TYPES)
    
    # Generate question
    max_retries = 3
    for attempt in range(max_retries):
        question = generate_question(selected_chunks, question_type)
        
        if question and question not in used_questions and len(question) > 10:
            used_questions.add(question)
            
            # Create the sample
            sample = {
                "question": question,
                "id": [chunk['id'] for chunk in selected_chunks],
                "chunk": [chunk['text'] for chunk in selected_chunks]
            }
            return sample
        
    return None

def main():
    print("Loading chunks...")
    all_chunks = load_chunks('rag_chunks_all.jsonl')
    print(f"Loaded {len(all_chunks)} chunks")
    
    print("Generating 400 evaluation samples...")
    samples = []
    used_questions = set()
    
    with open('rag_eval_dataset.jsonl', 'w', encoding='utf-8') as f:
        for i in range(400):
            sample = create_evaluation_sample(all_chunks, used_questions)
            
            if sample:
                # Write directly to file in JSONL format (one line per object)
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
                f.flush()
                print(f"Generated sample {i+1}/400", end='\r')
            else:
                print(f"\nFailed to generate sample {i+1}, retrying...")
                # Retry
                for retry in range(3):
                    sample = create_evaluation_sample(all_chunks, used_questions)
                    if sample:
                        f.write(json.dumps(sample, ensure_ascii=False) + '\n')
                        f.flush()
                        break
    
    print("\nDone! Output saved to rag_eval_dataset.jsonl")

if __name__ == "__main__":
    main()
