import asyncio
import unittest

from backend.services.vector_search import (
    close_ai_model_http_client,
    get_ai_model_http_client,
)


class VectorSearchHttpClientTests(unittest.TestCase):
    def tearDown(self):
        asyncio.run(close_ai_model_http_client())

    def test_reuses_single_async_client(self):
        first = get_ai_model_http_client()
        second = get_ai_model_http_client()

        self.assertIs(first, second)
        self.assertFalse(first.is_closed)

    def test_close_resets_singleton_client(self):
        first = get_ai_model_http_client()

        asyncio.run(close_ai_model_http_client())
        second = get_ai_model_http_client()

        self.assertTrue(first.is_closed)
        self.assertIsNot(first, second)
        self.assertFalse(second.is_closed)


if __name__ == "__main__":
    unittest.main()
