import unittest

import app as app_module


class GraphsPageTests(unittest.TestCase):
    def setUp(self):
        self.app_ctx = app_module.app.app_context()
        self.app_ctx.push()
        app_module.init()
        self.client = app_module.app.test_client()

    def tearDown(self):
        if self.app_ctx is not None:
            self.app_ctx.pop()
            self.app_ctx = None

    def test_graphs_page_exists(self):
        response = self.client.get("/graphs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Graphs", response.data)
        self.assertIn(b"amChart", response.data)


if __name__ == "__main__":
    unittest.main()
