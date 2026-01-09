"""
Script đọc tất cả file PDF trong folder và lưu nội dung sang file TXT
Sử dụng thư viện PyMuPDF (fitz) để trích xuất text từ PDF
"""

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
    """
    Loại bỏ số trang khỏi text (các dòng chỉ chứa số đứng riêng lẻ)
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Bỏ qua các dòng chỉ chứa số (số trang)
        # Hoặc các dòng như "Trang 1", "Page 1", "- 1 -", etc.
        if stripped.isdigit():
            continue
        if re.match(r'^[-–—\s]*\d+[-–—\s]*$', stripped):
            continue
        if re.match(r'^(Trang|Page|trang|page)\s*\d+$', stripped, re.IGNORECASE):
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Trích xuất toàn bộ text từ file PDF
    
    Args:
        pdf_path: Đường dẫn đến file PDF
        
    Returns:
        Nội dung text của file PDF
    """
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
    """
    Chuyển đổi tất cả file PDF trong folder sang file TXT
    
    Args:
        input_folder: Thư mục chứa các file PDF
        output_folder: Thư mục lưu file TXT (mặc định cùng thư mục với PDF)
    """
    input_path = Path(input_folder)
    
    # Nếu không chỉ định output folder, tạo subfolder 'txt_output'
    if output_folder is None:
        output_path = Path("output")
    else:
        output_path = Path(output_folder)
    
    # Tạo thư mục output nếu chưa tồn tại
    output_path.mkdir(exist_ok=True)
    
    # Tìm tất cả file PDF
    pdf_files = list(input_path.glob("*.pdf"))
    
    if not pdf_files:
        print(f"Không tìm thấy file PDF nào trong: {input_folder}")
        return
    
    print(f"Tìm thấy {len(pdf_files)} file PDF")
    print(f"Thư mục output: {output_path}")
    print("-" * 50)
    
    success_count = 0
    error_count = 0
    
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Đang xử lý: {pdf_file.name}")
        
        # Tạo tên file TXT (thay đổi extension)
        txt_filename = pdf_file.stem + ".txt"
        txt_path = output_path / txt_filename
        
        # Trích xuất text từ PDF
        text = extract_text_from_pdf(str(pdf_file))
        
        if text:
            # Lưu text vào file TXT với encoding UTF-8
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            print(f"  ✓ Đã lưu: {txt_filename}")
            success_count += 1
        else:
            print(f"  ✗ Không trích xuất được text từ file này")
            error_count += 1
    
    print("-" * 50)
    print(f"Hoàn thành!")
    print(f"  - Thành công: {success_count} file")
    print(f"  - Lỗi: {error_count} file")
    print(f"  - Thư mục output: {output_path}")


if __name__ == "__main__":
    # Đường dẫn thư mục hiện tại (chứa các file PDF)
    # current_folder = Path(__file__).parent
    
    # Chạy chuyển đổi
    convert_pdf_to_txt("tai_lieu_phap_luat")
