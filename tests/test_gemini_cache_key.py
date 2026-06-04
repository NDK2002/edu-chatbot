import unittest

from backend.services.gemini import build_cache_key


class GeminiCacheKeyTests(unittest.TestCase):
    def test_history_changes_cache_key(self):
        common = {
            "prompt": "vậy chu vi là gì?",
            "context": "Kiến thức Toán: chu vi là tổng độ dài các cạnh.",
            "grade": 3,
            "language": "vi",
            "role": "student",
        }

        rectangle_history = "Học sinh: hình chữ nhật là gì?\nTrợ lý: Hình chữ nhật có 2 chiều."
        square_history = "Học sinh: hình vuông là gì?\nTrợ lý: Hình vuông có 4 cạnh bằng nhau."

        self.assertNotEqual(
            build_cache_key(**common, history=rectangle_history),
            build_cache_key(**common, history=square_history),
        )

    def test_same_history_uses_same_cache_key(self):
        common = {
            "prompt": "vậy chu vi là gì?",
            "context": "Kiến thức Toán: chu vi là tổng độ dài các cạnh.",
            "grade": 3,
            "language": "vi",
            "role": "student",
            "history": "Học sinh: hình chữ nhật là gì?\nTrợ lý: Hình chữ nhật có 2 chiều.",
        }

        self.assertEqual(build_cache_key(**common), build_cache_key(**common))


if __name__ == "__main__":
    unittest.main()
