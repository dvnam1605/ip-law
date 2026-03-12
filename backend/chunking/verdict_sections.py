import re
from typing import List, Dict, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

MAX_CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " "],
)


def _split_oversized(chunks: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    result = []
    for content, label in chunks:
        if len(content) > MAX_CHUNK_SIZE:
            for j, sub in enumerate(_splitter.split_text(content)):
                suffix = f"-p{j+1}" if j > 0 else ""
                result.append((sub, f"{label}{suffix}"))
        else:
            result.append((content, label))
    return result


def macro_chunk(text: str) -> Dict[str, str]:
    """
    Split verdict into 4 macro sections.
    Uses "Vì các lẽ trên" as sentinel to locate the final QUYẾT ĐỊNH.
    """
    sections = {'header': '', 'noi_dung': '', 'nhan_dinh': '', 'quyet_dinh': ''}

    noi_dung_match = re.search(r'NỘI DUNG VỤ ÁN\s*:', text)
    nhan_dinh_match = re.search(r'NHẬN ĐỊNH CỦA TÒA ÁN\s*:', text)

    vi_cac_le_match = None
    for m in re.finditer(r'Vì các lẽ trên', text):
        vi_cac_le_match = m

    quyet_dinh_match = None
    if vi_cac_le_match:
        search_start = vi_cac_le_match.start()
        remaining = text[search_start:search_start + 500]
        qd_match = re.search(r'QUYẾT ĐỊNH\s*:', remaining)
        if qd_match:
            abs_start = search_start + qd_match.start()
            abs_end = search_start + qd_match.end()
            quyet_dinh_match = type('Match', (), {
                'start': staticmethod(lambda s=abs_start: s),
                'end': staticmethod(lambda e=abs_end: e),
            })()

    if not quyet_dinh_match:
        for m in re.finditer(r'(?m)^\s*QUYẾT ĐỊNH\s*:', text):
            quyet_dinh_match = m

    noi_dung_start = noi_dung_match.end() if noi_dung_match else 0
    if noi_dung_match:
        sections['header'] = text[:noi_dung_match.start()].strip()

    nhan_dinh_start = nhan_dinh_match.end() if nhan_dinh_match else noi_dung_start
    if nhan_dinh_match:
        sections['noi_dung'] = text[noi_dung_start:nhan_dinh_match.start()].strip()

    if quyet_dinh_match:
        sections['nhan_dinh'] = text[nhan_dinh_start:quyet_dinh_match.start()].strip()
        sections['quyet_dinh'] = text[quyet_dinh_match.end():].strip()
    else:
        sections['nhan_dinh'] = text[nhan_dinh_start:].strip()

    return sections


def micro_chunk_noi_dung(text: str) -> List[Tuple[str, str]]:
    """Split NỘI DUNG VỤ ÁN by party presentations. Returns [(content, party_role)]."""
    if not text.strip():
        return []

    party_patterns = [
        (r'(?:Nguyên đơn[^.]*?trình bày\s*:)', 'nguyên đơn'),
        (r'(?:Bị đơn[^.]*?trình bày\s*:)', 'bị đơn'),
        (r'(?:Người có quyền lợi[^.]*?trình bày\s*:)', 'người có quyền lợi'),
        (r'(?:Người kháng cáo[^.]*?trình bày\s*:)', 'người kháng cáo'),
        (r'(?:Viện [Kk]iểm sát[^.]*?(?:phát biểu|đề nghị)[^:]*:)', 'viện kiểm sát'),
        (r'(?:(?:Vị )?[Đđ]ại diện Viện [Kk]iểm sát[^.]*?phát biểu[^:]*:)', 'viện kiểm sát'),
        (r'(?:\*\s+(?:Yêu cầu|Theo đơn|Đại diện)[^\n]*:)', ''),
    ]
    lower_court_patterns = [
        r'Tại [Bb]ản án[^.]*sơ thẩm',
        r'Tại bản án kinh doanh[^.]*sơ thẩm',
    ]

    split_points = []
    for pattern, role in party_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            split_points.append((m.start(), m.end(), role or 'trình bày'))
    for pattern in lower_court_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            split_points.append((m.start(), m.end(), 'bản án sơ thẩm'))

    split_points.sort(key=lambda x: x[0])

    if not split_points:
        return [(text.strip(), 'nội dung')]

    chunks = []
    if split_points[0][0] > 50:
        intro = text[:split_points[0][0]].strip()
        if intro:
            chunks.append((intro, 'nội dung'))

    for i, (start, _end, role) in enumerate(split_points):
        next_start = split_points[i + 1][0] if i + 1 < len(split_points) else len(text)
        content = text[start:next_start].strip()
        if content:
            chunks.append((content, role))

    return _split_oversized(chunks)


def micro_chunk_nhan_dinh(text: str) -> List[Tuple[str, str]]:
    """Split NHẬN ĐỊNH section by numbered points [1], [2], [2.1], etc."""
    if not text.strip():
        return []

    points = list(re.finditer(r'\[(\d+(?:\.\d+)*)\]', text))
    if not points:
        return [(text.strip(), '')]

    chunks = []
    intro = text[:points[0].start()].strip()
    if intro and len(intro) > 30:
        chunks.append((intro, 'intro'))

    for i, match in enumerate(points):
        point_num = f"[{match.group(1)}]"
        end_pos = points[i + 1].start() if i + 1 < len(points) else len(text)
        content = text[match.start():end_pos].strip()
        if content:
            chunks.append((content, point_num))

    return _split_oversized(chunks)


def micro_chunk_quyet_dinh(text: str) -> List[Tuple[str, str]]:
    """
    Split QUYẾT ĐỊNH section by numbered items.
    Handles 4 numbering styles: N/., N., [N], Roman (I., II.)
    """
    if not text.strip():
        return []

    patterns = [
        (r'(?m)^\s*(\d+)/\.', 'slash'),
        (r'\[(\d+(?:\.\d+)*)\]', 'bracket'),
        (r'(?m)^\s*(I{1,3}|IV|VI{0,3}|IX|X{0,3})\.', 'roman'),
        (r'(?m)^\s*(\d+)\.\s', 'dot'),
    ]

    best_matches, best_style = [], ''
    for pattern, style in patterns:
        matches = list(re.finditer(pattern, text))
        if len(matches) > len(best_matches):
            best_matches, best_style = matches, style

    if not best_matches or len(best_matches) < 2:
        an_phi_match = re.search(r'(?:Án phí|án phí)', text)
        if an_phi_match and len(text[:an_phi_match.start()].strip()) > 50:
            return [
                (text[:an_phi_match.start()].strip(), 'quyết định'),
                (text[an_phi_match.start():].strip(), 'án phí'),
            ]
        return [(text.strip(), '')] if text.strip() else []

    style_format = {'slash': '{}/.',  'bracket': '[{}]', 'roman': '{}.', 'dot': '{}.'}
    fmt = style_format[best_style]

    chunks = []
    intro = text[:best_matches[0].start()].strip()
    if intro and len(intro) > 30:
        chunks.append((intro, 'căn cứ'))

    for i, match in enumerate(best_matches):
        item_num = fmt.format(match.group(1))
        end_pos = best_matches[i + 1].start() if i + 1 < len(best_matches) else len(text)
        content = text[match.start():end_pos].strip()
        if content:
            is_court_fee = bool(re.search(r'[Áá]n phí', content[:100], re.IGNORECASE))
            label = f"án phí {item_num}" if is_court_fee else item_num
            chunks.append((content, label))

    return _split_oversized(chunks)
