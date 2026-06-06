import unittest

from backend.services.orchestrator import QueryType, classify_query


class OrchestratorClassifyTests(unittest.TestCase):
    def test_detects_math_calculate(self):
        self.assertEqual(
            classify_query("chu vi hình chữ nhật dài 5cm rộng 3cm"),
            QueryType.MATH_CALCULATE,
        )

    def test_detects_math_theory(self):
        self.assertEqual(
            classify_query("chu vi hình chữ nhật là gì?"),
            QueryType.MATH_THEORY,
        )

    def test_detects_vietnamese_to_tay_dictionary(self):
        self.assertEqual(
            classify_query("dịch từ học sang tiếng Tày"),
            QueryType.DICT_VI_TAY,
        )

    def test_detects_short_unknown_word_as_tay_to_vietnamese(self):
        self.assertEqual(classify_query("slíp"), QueryType.DICT_TAY_VI)

    def test_detects_general_fallback(self):
        self.assertEqual(
            classify_query("hôm nay thời tiết thế nào?"),
            QueryType.GENERAL,
        )


if __name__ == "__main__":
    unittest.main()
