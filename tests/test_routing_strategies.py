import unittest
from backend.core.routing_strategies import classify_query_with_strategies, DEFAULT_STRATEGIES

class TestRoutingStrategies(unittest.TestCase):
    def test_legal_query(self):
        query = "Điều kiện bảo hộ quyền tác giả là gì?"
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'legal')

    def test_verdict_query(self):
        query = "Bản án về tranh chấp quyền tác giả đối với tác phẩm điện ảnh"
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'verdict')

    def test_trademark_search_query(self):
        query = "Tra cứu nhãn hiệu 'Coffee-VN' đã đăng ký chưa?"
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'trademark')

    def test_trademark_priority(self):
        # Even with 'kiện' (verdict signal), strong trademark signal should win
        query = "Tôi muốn tra cứu nhãn hiệu này để tránh bị kiện"
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'trademark')

    def test_advisory_combined_query(self):
        query = "Tôi phát hiện đối thủ sao chép logo của mình, tôi nên làm gì để khởi kiện?"
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'combined')

    def test_empty_query(self):
        query = ""
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'legal')

    def test_high_overlap_combined(self):
        # Has both legal (Điều, luật) and verdict (bồi thường, kiện) signals
        query = "Theo quy định tại Điều 200 Luật SHTT, mức bồi thường thiệt hại khi khởi kiện là bao nhiêu?"
        route = classify_query_with_strategies(query, DEFAULT_STRATEGIES)
        self.assertEqual(route, 'combined')

if __name__ == '__main__':
    unittest.main()
