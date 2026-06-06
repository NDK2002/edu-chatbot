import unittest
from unittest.mock import patch

from backend.services import vector_search


class VectorSearchResponseKeysTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_hit_response_uses_singular_score_keys(self):
        with (
            patch.object(vector_search, "_embed", return_value=[0.1, 0.2]),
            patch.object(vector_search, "get_client", return_value=object()),
            patch.object(vector_search, "_query_qdrant", return_value=[]),
        ):
            result = await vector_search.search("chu vi hình chữ nhật", grade=3)

        self.assertIn("top_vector_score", result)
        self.assertIn("top_rerank_score", result)
        self.assertNotIn("top_vector_scores", result)
        self.assertNotIn("top_rerank_scores", result)
        self.assertEqual(result["top_vector_score"], 0.0)
        self.assertIsNone(result["top_rerank_score"])


if __name__ == "__main__":
    unittest.main()
