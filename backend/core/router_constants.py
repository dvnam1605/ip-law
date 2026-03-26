import re
from typing import Literal

RouteType = Literal['legal', 'verdict', 'combined', 'trademark']

VERDICT_KEYWORDS = [
    r'tình huống', r'bồi thường', r'khởi kiện', r'kiện', r'phản tố',
    r'tòa\s*(án)?\s*(sẽ|đã|xử|xét)', r'bị đơn', r'nguyên đơn',
    r'bản án', r'án lệ', r'xâm phạm', r'vi phạm.*quyền',
    r'thiệt hại', r'bồi hoàn', r'xin lỗi.*công khai', r'đăng báo',
    r'công ty.*(?:tôi|chúng tôi)', r'tôi\s*(?:phát hiện|muốn|cần|nên)',
    r'nên\s*(?:làm|xử lý|kiện|khởi)', r'hướng giải quyết',
    r'phán quyết', r'nhận định', r'tranh chấp',
    r'sao chép', r'hàng nhái', r'hàng giả',
]

LEGAL_KEYWORDS = [
    r'(?:điều|khoản)\s*\d+', r'quy định', r'luật\s+(?:nào|gì|nói)',
    r'thủ tục', r'điều kiện\s*(?:đăng ký|cấp|bảo hộ)',
    r'thời hạn\s*(?:bảo hộ|đăng ký|khiếu nại)',
    r'nghị định', r'thông tư', r'hướng dẫn',
    r'đối tượng.*bảo hộ', r'quyền.*(?:tác giả|sáng chế|nhãn hiệu)',
    r'đăng ký.*(?:nhãn hiệu|sáng chế|kiểu dáng)',
    r'(?:mức|hình thức).*xử phạt', r'phân biệt.*(?:giữa|và)',
]

TRADEMARK_KEYWORDS = [
    r'tra\s*cứu.*nhãn\s*hiệu', r'nhãn\s*hiệu.*đã\s*đăng\s*ký',
    r'nhãn\s*hiệu.*tương\s*tự', r'xung\s*đột.*nhãn\s*hiệu',
    r'đăng\s*ký.*nhãn\s*hiệu.*(?:chưa|được\s*không|có\s*thể)',
    r'kiểm\s*tra.*nhãn\s*hiệu', r'trademark',
    r'tên\s*thương\s*(?:mại|hiệu).*(?:trùng|giống|tương\s*tự)',
    r'brand.*(?:search|lookup|check)',
    r'nhãn\s*hiệu.*(?:trùng|giống|xem|check|có\s*ai)',
    r'logo.*(?:đã\s*đăng\s*ký|trùng|giống)',
    r'thương\s*hiệu.*(?:đã\s*có|đã\s*đăng|trùng|xung\s*đột)',
]

ADVISORY_PATTERNS = [
    r'(?:tôi|chúng tôi)\s*(?:phát hiện|phát\s*hiện\s*ra).*(?:nên|cần|phải|làm)',
    r'(?:nên|cần|phải)\s*(?:làm\s*(?:gì|thế\s*nào|sao)|xử\s*lý\s*(?:thế\s*nào|ra\s*sao))',
    r'(?:bước|cách)\s*(?:xử\s*lý|giải\s*quyết|khiếu\s*nại|khởi\s*kiện)',
    r'(?:tôi|chúng tôi)\s*(?:bị|đã bị|đang bị).*(?:nên|cần|phải|làm)',
    r'(?:phát hiện|phát\shien).*(?:sử dụng|dùng|copy|sao chép|làm nhái|làm giả)',
    r'(?:xử\s*lý|giải\s*quyết|bảo\s*vệ).*(?:thế\s*nào|như\s*thế\s*nào|ra\s*sao)',
    r'(?:tôi|chúng tôi).*(?:logo|nhãn hiệu|thương hiệu|sáng chế|tác phẩm|thiết kế).*(?:bị|đang)',
    r'(?:bên khác|đối thủ|công ty khác|người khác).*(?:sử dụng|dùng|copy|sao chép|bắt chước)',
]

COMBINED_SYSTEM_PROMPT = """Bạn là Chuyên gia Pháp lý AI chuyên tư vấn Luật Sở hữu trí tuệ Việt Nam. Bạn có 2 nguồn dữ liệu:
- [VĂN BẢN PHÁP LUẬT]: Các điều luật, nghị định, thông tư hiện hành
- [BẢN ÁN THAM KHẢO]: Các bản án thực tế đã xét xử

## NGUYÊN TẮC TUYỆT ĐỐI:
1. **ZERO HALLUCINATION**: CHỈ trích dẫn điều luật và bản án có trong dữ liệu bên dưới. KHÔNG tự bịa ra bất kỳ số hiệu văn bản, số bản án, hay nội dung nào không có trong nguồn cung cấp.
2. Phân biệt rõ: đâu là quy định pháp luật (nên, phải, được phép) và đâu là thực tiễn xét xử (Tòa đã xử thế nào).
3. Ngôn ngữ thận trọng: "Dựa trên thực tiễn xét xử...", "Theo quy định tại...", "Nhiều khả năng..."
4. Nếu dữ liệu không đủ, thừa nhận giới hạn.

## CÁCH TRẢ LỜI:

1. **Vấn đề pháp lý**: Xác định vấn đề cốt lõi (2-3 câu).

2. **Cơ sở pháp luật**: Trích dẫn các điều luật liên quan từ [VĂN BẢN PHÁP LUẬT]:
   - Quyền của chủ sở hữu, hành vi bị cấm, thủ tục xử lý
   - Trích: "Theo Điều X Luật Y..."

3. **Thực tiễn xét xử**: Đối chiếu với [BẢN ÁN THAM KHẢO] (CHỈ các bản án có trong danh sách):
   - Tòa đã nhận định và phán quyết thế nào trong vụ tương tự
   - Trích: "Theo Bản án số X, Tòa nhận định..."

4. **Tư vấn hướng xử lý**: Kết hợp cả luật và thực tiễn:
   - Các bước nên làm (theo quy trình luật định)
   - Dự đoán kết quả (dựa trên bản án tương tự)
   - Mức bồi thường/xử phạt tham khảo

5. **Kết luận**: Lời khuyên chốt lại + nhắc tham vấn luật sư.
"""

# Pre-compile patterns for performance
VERDICT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in VERDICT_KEYWORDS]
LEGAL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in LEGAL_KEYWORDS]
TRADEMARK_PATTERNS = [re.compile(p, re.IGNORECASE) for p in TRADEMARK_KEYWORDS]
ADVISORY_COMPILED = [re.compile(p, re.IGNORECASE) for p in ADVISORY_PATTERNS]
