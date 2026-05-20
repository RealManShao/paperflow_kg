import os
import base64
import unittest
import requests
from requests.auth import HTTPBasicAuth


NEO4J_URL = os.getenv("NEO4J_QUERY_API_URL", "https://57848aa8.databases.neo4j.io/db/57848aa8/query/v2")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "57848aa8")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fUd3NQz35sxryBBLbHZ1vdxbXE4sgDzIxNTADdlMNsM")


def _basic_auth_header(username, password):
    raw = f"{username}:{password}"
    encoded = base64.b64encode(raw.encode()).decode()
    return f"Basic {encoded}"


class TestNeo4jQueryAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = NEO4J_URL
        cls.auth = HTTPBasicAuth(NEO4J_USERNAME, NEO4J_PASSWORD)
        cls.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, statement, parameters=None):
        body = {"statement": statement}
        if parameters:
            body["parameters"] = parameters
        try:
            return requests.post(
                self.url,
                json=body,
                auth=self.auth,
                headers=self.headers,
                timeout=15,
                verify=False,
            )
        except Exception as e:
            raise unittest.SkipTest(f"Neo4j unreachable: {e}")

    def test_basic_auth_header_format(self):
        header = _basic_auth_header(NEO4J_USERNAME, NEO4J_PASSWORD)
        expected = "Basic " + base64.b64encode(f"{NEO4J_USERNAME}:{NEO4J_PASSWORD}".encode()).decode()
        self.assertEqual(header, expected)
        self.assertTrue(header.startswith("Basic "))

    def test_query_match_nodes(self):
        resp = self._post(
            "MATCH (n) RETURN n.id, n.name, labels(n)[0] AS type LIMIT 3"
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("data", data)
        result_data = data["data"]
        self.assertIn("fields", result_data)
        self.assertIn("values", result_data)
        self.assertGreaterEqual(len(result_data["values"]), 1)

        first = result_data["values"][0]
        self.assertEqual(len(first), 3)

    def test_query_with_parameters(self):
        resp = self._post(
            "MATCH (p:Paper {id: $pid}) RETURN p.id, p.name",
            {"pid": "7C7CAEED"},
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        values = data["data"]["values"]
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0][0], "7C7CAEED")

    def test_query_returns_error_on_bad_syntax(self):
        resp = self._post("MATCH (n INVALID SYNTAX")
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("errors", body)

    def test_header_content_type_is_json(self):
        self.assertEqual(self.headers["Content-Type"], "application/json")

    def test_auth_is_basic(self):
        self.assertIsInstance(self.auth, HTTPBasicAuth)


if __name__ == "__main__":
    unittest.main(verbosity=2)
