import os
import requests
from requests.auth import HTTPBasicAuth


NEO4J_URL = os.getenv("NEO4J_URL", "https://57848aa8.databases.neo4j.io/db/57848aa8/query/v2")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "57848aa8")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fUd3NQz35sxryBBLbHZ1vdxbXE4sgDzIxNTADdlMNsM")


class Reasoner:
    def __init__(self, url=None, username=None, password=None):
        self.url = url or NEO4J_URL
        self.auth = HTTPBasicAuth(username or NEO4J_USERNAME, password or NEO4J_PASSWORD)

    def _run(self, query, parameters=None):
        body = {"statement": query}
        if parameters:
            body["parameters"] = parameters
        resp = requests.post(self.url, json=body, auth=self.auth, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        result_data = data.get("data", {})
        fields = result_data.get("fields", [])
        values = result_data.get("values", [])
        return [dict(zip(fields, row)) for row in values]

    def find_shortest_path(self, source_id, target_id, max_hops=5):
        query = f"""
        MATCH path = shortestPath((source {{id: $source_id}})-[*1..{max_hops}]-(target {{id: $target_id}}))
        RETURN path
        LIMIT 1
        """
        results = self._run(query, {"source_id": source_id, "target_id": target_id})
        if not results:
            return None
        return self._parse_path(results[0]["path"])

    def find_all_paths(self, source_id, target_id, max_hops=3, limit=10):
        query = f"""
        MATCH path = (source {{id: $source_id}})-[*1..{max_hops}]-(target {{id: $target_id}})
        WHERE source <> target
        RETURN path
        LIMIT $limit
        """
        results = self._run(query, {"source_id": source_id, "target_id": target_id, "limit": limit})
        return [self._parse_path(r["path"]) for r in results]

    def bfs_from_entity(self, entity_id, max_depth=2, rel_types=None):
        if rel_types:
            types_str = "|".join([f":{t}" for t in rel_types])
            type_filter = f"-[r:{types_str}]-"
        else:
            type_filter = "-[r]-"

        query = f"""
        MATCH path = (start {{id: $entity_id}}) {type_filter}*1..{max_depth} (neighbor)
        WHERE neighbor <> start
        RETURN DISTINCT neighbor.id AS id, neighbor.name AS name,
               labels(neighbor)[0] AS type,
               length(path) AS depth,
               [rel IN relationships(path) | type(rel)] AS rel_chain
        ORDER BY depth
        """
        return self._run(query, {"entity_id": entity_id})

    def find_common_neighbors(self, entity_id1, entity_id2):
        query = """
        MATCH (a {id: $id1})--(common)--(b {id: $id2})
        RETURN common.id AS id, common.name AS name, labels(common)[0] AS type
        """
        return self._run(query, {"id1": entity_id1, "id2": entity_id2})

    def find_collaboration_path(self, author_id1, author_id2, max_hops=4):
        query = f"""
        MATCH path = shortestPath(
            (a1:Author {{id: $author_id1}})-[:WRITES|CITES*1..{max_hops}]-(a2:Author {{id: $author_id2}})
        )
        RETURN path
        LIMIT 1
        """
        results = self._run(query, {"author_id1": author_id1, "author_id2": author_id2})
        if not results:
            return None
        return self._parse_path(results[0]["path"])

    def find_citation_chain(self, source_paper_id, target_paper_id, max_hops=5):
        query = f"""
        MATCH path = shortestPath(
            (source:Paper {{id: $source_id}})-[:CITES*1..{max_hops}]->(target:Paper {{id: $target_id}})
        )
        RETURN path
        LIMIT 1
        """
        results = self._run(query, {"source_id": source_paper_id, "target_id": target_paper_id})
        if not results:
            return None
        return self._parse_path(results[0]["path"])

    def find_papers_by_author_and_domain(self, author_id, domain_id):
        query = """
        MATCH (a:Author {id: $author_id})-[:WRITES]->(p:Paper)-[:BELONGS_TO_DOMAIN]->(d:Domain {id: $domain_id})
        RETURN p.id AS id, p.name AS title, d.name AS domain
        """
        return self._run(query, {"author_id": author_id, "domain_id": domain_id})

    def find_influential_papers(self, domain_id=None, limit=10):
        domain_filter = ""
        params = {"limit": limit}
        if domain_id:
            domain_filter = "-[:BELONGS_TO_DOMAIN]->(d:Domain {id: $domain_id})"
            params["domain_id"] = domain_id

        query = f"""
        MATCH (p:Paper) {domain_filter}
        OPTIONAL MATCH (p)<-[:CITES]-(citer:Paper)
        RETURN p.id AS id, p.name AS title, count(DISTINCT citer) AS citation_count
        ORDER BY citation_count DESC
        LIMIT $limit
        """
        return self._run(query, params)

    def find_similar_papers(self, paper_id, via="domain", limit=5):
        if via == "domain":
            query = """
            MATCH (p:Paper {id: $paper_id})-[:BELONGS_TO_DOMAIN]->(d:Domain)<-[:BELONGS_TO_DOMAIN]-(other:Paper)
            WHERE other <> p
            RETURN other.id AS id, other.name AS title, count(DISTINCT d) AS shared_domains
            ORDER BY shared_domains DESC
            LIMIT $limit
            """
        elif via == "author":
            query = """
            MATCH (p:Paper {id: $paper_id})<-[:WRITES]-(a:Author)-[:WRITES]->(other:Paper)
            WHERE other <> p
            RETURN other.id AS id, other.name AS title, count(DISTINCT a) AS shared_authors
            ORDER BY shared_authors DESC
            LIMIT $limit
            """
        elif via == "citation":
            query = """
            MATCH (p:Paper {id: $paper_id})-[:CITES]->(cited:Paper)<-[:CITES]-(other:Paper)
            WHERE other <> p
            RETURN other.id AS id, other.name AS title, count(DISTINCT cited) AS shared_citations
            ORDER BY shared_citations DESC
            LIMIT $limit
            """
        else:
            return []

        return self._run(query, {"paper_id": paper_id, "limit": limit})

    def get_author_centrality(self, metric="degree", limit=10):
        if metric == "degree":
            query = """
            MATCH (a:Author)-[:WRITES]->(p:Paper)
            RETURN a.id AS id, a.name AS name, count(DISTINCT p) AS paper_count
            ORDER BY paper_count DESC
            LIMIT $limit
            """
        elif metric == "citation":
            query = """
            MATCH (a:Author)-[:WRITES]->(p:Paper)<-[:CITES]-(citer:Paper)
            RETURN a.id AS id, a.name AS name, count(DISTINCT citer) AS total_citations
            ORDER BY total_citations DESC
            LIMIT $limit
            """
        else:
            return []

        return self._run(query, {"limit": limit})

    def _parse_path(self, path):
        if path is None:
            return None

        chain = []
        for i in range(0, len(path) - 2, 2):
            start_node = path[i]
            rel = path[i + 1]
            end_node = path[i + 2]

            def _node_info(n):
                return {
                    "id": n.get("properties", {}).get("id"),
                    "name": n.get("properties", {}).get("name"),
                    "type": n.get("labels", [None])[0] if n.get("labels") else None,
                }

            chain.append({
                "source": _node_info(start_node),
                "relation": rel.get("type"),
                "target": _node_info(end_node),
            })
        return chain

    def format_reasoning_chain(self, chain, title="Reasoning Chain"):
        if not chain:
            return f"## {title}\nNo path found."

        lines = [f"## {title}"]
        for i, step in enumerate(chain):
            src = step["source"]
            tgt = step["target"]
            rel = step["relation"]
            src_name = src.get("name", src.get("id", "?"))
            tgt_name = tgt.get("name", tgt.get("id", "?"))
            lines.append(f"  {i+1}. [{src_name}] --{rel}--> [{tgt_name}]")
        return "\n".join(lines)
