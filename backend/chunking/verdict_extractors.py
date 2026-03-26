import re
from typing import List, Tuple


def clean_ocr_artifacts(text: str) -> str:
    text = re.sub(r'(?m)^\s*(\d+(?:\.\d+)*)\s*(?=\s+[A-ZĐ])', r'[\1]', text)
    text = re.sub(r'\[(\d+(?:\.\d+)*)\s+(?=[A-ZĐa-zđ])', r'[\1] ', text)
    text = re.sub(r'\[\s+(\d+(?:\.\d+)*)\]', r'[\1]', text)
    text = re.sub(r'[ \t]{3,}', '  ', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text


def extract_case_number(text: str) -> str:
    for pattern in [
        r'Bản án số[:\s]*(\d+/\d{4}/[A-ZĐa-zđ\-]+)',
        r'BẢN ÁN SỐ[:\s]*(\d+/\d{4}/[A-ZĐa-zđ\-]+)',
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def extract_case_number_from_filename(filename: str) -> str:
    match = re.match(r'BA\s*(\d+)\s*-\s*(\d{4})', filename)
    return f"{match.group(1)}/{match.group(2)}" if match else filename


def extract_court_name(text: str) -> str:
    for pattern in [
        r'(TÒA ÁN NHÂN DÂN\s+CẤP CAO\s+TẠI\s+[^\n]+)',
        r'(TOÀ ÁN NHÂN DÂN\s+CẤP CAO\s+TẠI\s+[^\n]+)',
        r'(TÒA ÁN NHÂN DÂN\s+[^\n]+)',
    ]:
        match = re.search(pattern, text)
        if match:
            return re.sub(r'\s+', ' ', match.group(1).strip())
    return ""


def extract_judgment_date(text: str) -> str:
    for pattern in [
        r'Ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})',
        r'Ngày[:\s]*(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})',
        r'Ngày[:\s]*(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{4})',
    ]:
        match = re.search(pattern, text)
        if match:
            d, m, y = match.group(1), match.group(2), match.group(3)
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return ""


def extract_dispute_type(text: str) -> str:
    for pattern in [
        r'V/v[.:\s]*["\u201c]?([^\n"\u201d]+)["\u201d]?',
        r'về việc\s*["\u201c]?([^\n"\u201d]+)["\u201d]?',
    ]:
        match = re.search(pattern, text[:2000], re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip('.')
    return ""


def extract_trial_level(text: str, case_number: str) -> str:
    if case_number:
        upper = case_number.upper()
        if '-PT' in upper or 'PT' in upper:
            return "phúc thẩm"
        if '-ST' in upper:
            return "sơ thẩm"
        if '-GĐT' in upper:
            return "giám đốc thẩm"

    text_lower = text[:3000].lower()
    if 'phúc thẩm' in text_lower:
        return "phúc thẩm"
    if 'sơ thẩm' in text_lower and 'phúc thẩm' not in text_lower:
        return "sơ thẩm"
    return ""


def extract_parties(text: str) -> Tuple[str, str, str]:
    header = text[:3000]

    plaintiff = ""
    match = re.search(r'[-–]?\s*Nguyên đơn\s*:\s*([^\n]+)', header, re.IGNORECASE)
    if match:
        plaintiff = match.group(1).strip().rstrip(';')

    defendant = ""
    match = re.search(r'[-–]?\s*Bị đơn\s*:\s*([^\n]+)', header, re.IGNORECASE)
    if match:
        defendant = match.group(1).strip().rstrip(';')

    third_party = ""
    match = re.search(r'[-–]?\s*Người có quyền lợi[^:]*:\s*([^\n]+)', header, re.IGNORECASE)
    if match:
        third_party = match.group(1).strip().rstrip(';')

    return plaintiff, defendant, third_party


def extract_judges(text: str) -> str:
    judges = []
    header = text[:2000]

    match = re.search(r'Chủ tọa phiên tòa\s*:\s*([^\n]+)', header, re.IGNORECASE)
    if match:
        judges.append(match.group(1).strip())

    match = re.search(
        r'Các Thẩm phán\s*:\s*([^\n]+(?:\n[^\n]*(?:Ông|Bà)[^\n]*)*)',
        header, re.IGNORECASE,
    )
    if match:
        names = re.findall(r'(?:Ông|Bà)\s+([^;,\n]+)', match.group(1).strip())
        judges.extend(n.strip().rstrip('.') for n in names)

    return "; ".join(judges) if judges else ""


_IP_KEYWORDS = {
    "nhãn hiệu": ["nhãn hiệu", "GCNĐKNH", "GCN ĐKNH", "đăng ký nhãn hiệu"],
    "sáng chế": ["sáng chế", "Bằng độc quyền sáng chế", "patent"],
    "quyền tác giả": ["quyền tác giả", "bản quyền tác phẩm", "bản quyền", "phần mềm máy tính"],
    "kiểu dáng công nghiệp": ["kiểu dáng công nghiệp", "GCNĐKKDCN"],
    "bí mật kinh doanh": ["bí mật kinh doanh", "bí mật thương mại"],
    "tên thương mại": ["tên thương mại"],
    "chỉ dẫn địa lý": ["chỉ dẫn địa lý"],
}


def detect_ip_types(text: str) -> List[str]:
    text_lower = text.lower()
    detected = [
        ip_type
        for ip_type, keywords in _IP_KEYWORDS.items()
        if any(kw.lower() in text_lower for kw in keywords)
    ]
    return detected or ["sở hữu trí tuệ"]


def extract_law_references(text: str) -> List[str]:
    matches = re.findall(
        r'(?:điểm\s+\w+\s+)?(?:khoản\s+\d+\s+)?Điều\s+\d+[a-zđ]?'
        r'\s+(?:Luật|Bộ luật|Nghị định|Thông tư)[^,;\n]{5,60}',
        text, re.IGNORECASE,
    )
    return sorted(set(m.strip() for m in matches))[:30]


def generate_summary(metadata: dict) -> str:
    parts = []
    if metadata.get('case_number'):
        parts.append(f"Bản án số {metadata['case_number']}")
    if metadata.get('dispute_type'):
        parts.append(metadata['dispute_type'])
    if metadata.get('plaintiff') and metadata.get('defendant'):
        parts.append(f"giữa {metadata['plaintiff']} và {metadata['defendant']}")
    if metadata.get('trial_level'):
        parts.append(f"cấp {metadata['trial_level']}")
    if metadata.get('court_name'):
        parts.append(f"tại {metadata['court_name']}")
    return ", ".join(parts)
