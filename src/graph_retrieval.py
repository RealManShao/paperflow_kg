import os
import requests
from requests.auth import HTTPBasicAuth

from dotenv import load_dotenv

load_dotenv()


NEO4J_QUERY_API_URL = os.getenv("NEO4J_QUERY_API_URL")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

NEO4J_VERIFY_SSL = os.getenv("NEO4J_VERIFY_SSL", "true").lower() not in ("0", "false", "no")


class GraphRetriever:
    def __init__(self, url=None, username=None, password=None):
        self.url = url or NEO4J_QUERY_API_URL
        if not self.url:
            raise ValueError("Missing NEO4J_QUERY_API_URL.")
        user = username or NEO4J_USERNAME
        pwd = password or NEO4J_PASSWORD
        if not user or not pwd:
            raise ValueError("Missing Neo4j credentials. Set NEO4J_USERNAME and NEO4J_PASSWORD.")
        self.auth = HTTPBasicAuth(user, pwd)

    def _run(self, query, parameters=None):
        body = {"statement": query}
        if parameters:
            body["parameters"] = parameters
        resp = requests.post(self.url, json=body, auth=self.auth, timeout=30, verify=NEO4J_VERIFY_SSL)
        resp.raise_for_status()
        data = resp.json()
        result_data = data.get("data", {})
        fields = result_data.get("fields", [])
        values = result_data.get("values", [])
        return [dict(zip(fields, row)) for row in values]

    def find_entity_by_name(self, name, label=None, limit=5):
        where_clause = f"AND n:{label}" if label else ""
        query = f"""
        MATCH (n)
        WHERE toLower(n.name) CONTAINS toLower($name) {where_clause}
        RETURN n.id AS id, n.name AS name, labels(n)[0] AS type
        LIMIT $limit
        """
        return self._run(query, {"name": name, "limit": limit})

    def get_entity_by_id(self, entity_id):
        query = """
        MATCH (n {id: $entity_id})
        RETURN n.id AS id, n.name AS name, labels(n)[0] AS type
        """
        results = self._run(query, {"entity_id": entity_id})
        return results[0] if results else None

    def get_paper_cites(self, paper_id):
        query = """
        MATCH (p:Paper {id: $paper_id})-[:CITES]->(cited:Paper)
        RETURN cited.id AS id, cited.name AS title
        """
        return self._run(query, {"paper_id": paper_id})

    def get_paper_cited_by(self, paper_id):
        query = """
        MATCH (citer:Paper)-[:CITES]->(p:Paper {id: $paper_id})
        RETURN citer.id AS id, citer.name AS title
        """
        return self._run(query, {"paper_id": paper_id})

    def get_paper_conference(self, paper_id):
        query = """
        MATCH (p:Paper {id: $paper_id})-[:PUBLISHED_IN]->(conf:Conference)
        RETURN conf.id AS id, conf.name AS name
        """
        results = self._run(query, {"paper_id": paper_id})
        return results[0] if results else None

    def get_paper_domains(self, paper_id):
        query = """
        MATCH (p:Paper {id: $paper_id})-[:BELONGS_TO_DOMAIN]->(domain:Domain)
        RETURN domain.id AS id, domain.name AS name
        """
        return self._run(query, {"paper_id": paper_id})

    def get_paper_authors(self, paper_id):
        query = """
        MATCH (author:Author)-[:WRITES]->(p:Paper {id: $paper_id})
        RETURN author.id AS id, author.name AS name
        """
        return self._run(query, {"paper_id": paper_id})

    def get_author_papers(self, author_id):
        query = """
        MATCH (a:Author {id: $author_id})-[:WRITES]->(p:Paper)
        RETURN p.id AS id, p.name AS title
        """
        return self._run(query, {"author_id": author_id})

    def get_affiliation_authors(self, affiliation_id):
        query = """
        MATCH (aff:Affiliation {id: $affiliation_id})<-[:BELONGS_TO_AFFILIATION]-(author:Author)
        RETURN author.id AS id, author.name AS name
        """
        return self._run(query, {"affiliation_id": affiliation_id})

    def get_paper_details(self, paper_id):
        authors = self.get_paper_authors(paper_id)
        cites = self.get_paper_cites(paper_id)
        cited_by = self.get_paper_cited_by(paper_id)
        conference = self.get_paper_conference(paper_id)
        domains = self.get_paper_domains(paper_id)

        entity = self.get_entity_by_id(paper_id)
        if not entity:
            return None

        return {
            "id": entity["id"],
            "title": entity["name"],
            "type": entity["type"],
            "authors": [{"id": r["id"], "name": r["name"]} for r in authors],
            "cites": [{"id": r["id"], "title": r["title"]} for r in cites],
            "cited_by": [{"id": r["id"], "title": r["title"]} for r in cited_by],
            "conference": {"id": conference["id"], "name": conference["name"]} if conference else None,
            "domains": [{"id": r["id"], "name": r["name"]} for r in domains],
        }

    def get_k_hop_neighbors(self, entity_id, k=1, direction="both"):
        if direction == "outgoing":
            rel_pattern = "-[r]->"
        elif direction == "incoming":
            rel_pattern = "<-[r]-"
        else:
            rel_pattern = "-[r]-"

        if k == 1:
            query = f"""
            MATCH (start {{id: $entity_id}}) {rel_pattern} (neighbor)
            RETURN neighbor.id AS id, neighbor.name AS name,
                   labels(neighbor)[0] AS type, type(r) AS relation
            """
        else:
            query = f"""
            MATCH path = (start {{id: $entity_id}}) {rel_pattern}*{k} (neighbor)
            WHERE neighbor <> start
            RETURN neighbor.id AS id, neighbor.name AS name,
                   labels(neighbor)[0] AS type,
                   [rel IN relationships(path) | type(rel)] AS relations,
                   length(path) AS hops
            ORDER BY hops
            """
        return self._run(query, {"entity_id": entity_id})

    def get_subgraph(self, entity_ids, k=1):
        placeholders = ", ".join(["$eid" + str(i) for i in range(len(entity_ids))])
        params = {"k": k}
        for i, eid in enumerate(entity_ids):
            params["eid" + str(i)] = eid

        query = f"""
        MATCH (start) WHERE start.id IN [{placeholders}]
        MATCH path = (start) -[*1..{k}]- (neighbor)
        WITH nodes(path) AS nodes, relationships(path) AS rels
        UNWIND nodes AS n
        UNWIND rels AS r
        RETURN DISTINCT n.id AS id, n.name AS name, labels(n)[0] AS type
        UNION
        MATCH ()-[r]->()
        WHERE id(r) IN [id(r) | r IN rels]
        RETURN DISTINCT startNode(r).id AS source_id, type(r) AS relation, endNode(r).id AS target_id
        """
        return self._run(query, params)

    def get_path_between(self, source_id, target_id, max_hops=3):
        query = f"""
        MATCH path = shortestPath((source {{id: $source_id}})-[*1..{max_hops}]-(target {{id: $target_id}}))
        RETURN path
        LIMIT 1
        """
        results = self._run(query, {"source_id": source_id, "target_id": target_id})
        if not results:
            return None

        path = results[0]["path"]
        return self._parse_path(path)

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

    def format_evidence(self, results, title="Graph Evidence"):
        lines = [f"## {title}"]
        for record in results:
            parts = [f"{k}: {v}" for k, v in record.items() if v]
            lines.append("  " + ", ".join(parts))
        return "\n".join(lines) if len(lines) > 1 else "No evidence found."
