import os
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Đang cài đặt thư viện PyMuPDF...")
    os.system("pip install pymupdf")
    import fitz


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
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def extract_text_from_pdf(pdf_path: str) -> str:

    text_content = []
    
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            page_text = page.get_text()
            if page_text:
                # Lọc bỏ số trang
                cleaned_text = remove_page_numbers(page_text.strip())
                if cleaned_text.strip():
                    text_content.append(cleaned_text)
        doc.close()
    except Exception as e:
        print(f"  Lỗi khi đọc file: {e}")
        return ""
    
    return "\n\n".join(text_content)


def convert_pdf_to_txt(input_folder: str, output_folder: str = None):
    input_path = Path(input_folder)
    
    if output_folder is None:
        output_path = Path("output")
    else:
        output_path = Path(output_folder)
    
    output_path.mkdir(exist_ok=True)
    
    pdf_files = list(input_path.glob("*.pdf"))
    
    if not pdf_files:
        return
    
    success_count = 0
    error_count = 0
    
    for i, pdf_file in enumerate(pdf_files, 1):
        txt_filename = pdf_file.stem + ".txt"
        txt_path = output_path / txt_filename
        
        text = extract_text_from_pdf(str(pdf_file))
        
        if text:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            success_count += 1
        else:
            error_count += 1

if __name__ == "__main__":
    convert_pdf_to_txt("ban-an", "output-ban-an")
