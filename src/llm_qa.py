import os
import json
import argparse
from textwrap import dedent

import requests
from requests.auth import HTTPBasicAuth
import urllib3
from openai import OpenAI


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


NEO4J_QUERY_API_URL = os.getenv("NEO4J_QUERY_API_URL", "https://57848aa8.databases.neo4j.io/db/57848aa8/query/v2")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "57848aa8")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fUd3NQz35sxryBBLbHZ1vdxbXE4sgDzIxNTADdlMNsM")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api-inference.modelscope.cn/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ms-8018a0a9-2caa-4cfb-bc64-0ba0a736fc2e")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen3-8B")


GRAPH_SCHEMA = dedent("""\
Node properties:
  Paper {id: STRING, name: STRING}
  Author {id: STRING, name: STRING}
  Conference {id: STRING, name: STRING}
  Domain {id: STRING, name: STRING}
  Affiliation {id: STRING, name: STRING}

Relationships:
  (:Author)-[:WRITES]->(:Paper)
  (:Paper)-[:CITES]->(:Paper)
  (:Paper)-[:PUBLISHED_IN]->(:Conference)
  (:Paper)-[:BELONGS_TO_DOMAIN]->(:Domain)
  (:Author)-[:BELONGS_TO_AFFILIATION]->(:Affiliation)
""")


CYPHER_EXAMPLES = dedent("""\
/* Example 1: Find papers in a specific domain with high citation count */
MATCH (p:Paper)-[:BELONGS_TO_DOMAIN]->(d:Domain {name: "Algorithm"})
MATCH (p)<-[:CITES]-(c:Paper)
WITH p, count(c) AS citationCount
WHERE citationCount > 5
RETURN p.name
LIMIT 5

/* Example 2: Find all papers written by an author and their citations */
MATCH (a:Author {name: 'ralf sarlette'})-[w:WRITES]->(p:Paper)
OPTIONAL MATCH (p)-[c:CITES]->(cited:Paper)
RETURN p.name AS PaperName, p.id AS PaperID, cited.name AS CitedPaperName, cited.id AS CitedPaperID

/* Example 3: Find papers in a domain published in specific conferences */
MATCH (p:Paper)-[BELONGS_TO_DOMAIN]->(d:Domain {name: 'Software architecture'})
MATCH (p)-[PUBLISHED_IN]->(c:Conference)
WHERE c.name IN ['AAAI']
RETURN p.name AS paper, d.name AS domain, c.name AS conference
""")

CYPHER_GENERATION_PROMPT = dedent("""\
You are a Neo4j Cypher expert. Given the graph schema and a user question, generate a valid Cypher query using multi-jump method for complex questions.

Schema:
{schema}

Multi-Jump Method for Complex Queries:
- Break down complex questions into multiple MATCH clauses to traverse relationships step by step
- Use WITH clauses to aggregate or filter intermediate results
- Apply aggregation functions (count, max, min, avg) when needed
- Use WHERE clauses after WITH to filter aggregated results

Schema Examples:
{examples}

Rules:
- Use only the node labels and relationship types from the schema.
- The relationship direction is strictly defined as in the schema, do NOT reverse it.
- Return name fields for nodes.
- Return LIMIT 10 unless specified otherwise.
- Do NOT use shortestPath() with variable-length path bounds as parameters.
- For complex questions, use multiple MATCH and WITH clauses to navigate the graph

User question: {question}

Return ONLY the Cypher query, no explanation, no markdown.
""")


ANSWER_PROMPT = dedent("""\
You are a research assistant. Use the graph query results to answer the user's question.

Graph schema:
{schema}

Question: {question}

Cypher query used:
{cypher}

Query results:
{results}

Answer the question concisely based on the results. If the results are empty, say so.
""")


class GraphRAG:
    def __init__(self, neo4j_url=None, neo4j_username=None, neo4j_password=None,
                 llm_base_url=None, llm_api_key=None, llm_model=None):
        self.neo4j_url = neo4j_url or NEO4J_QUERY_API_URL
        self.neo4j_auth = HTTPBasicAuth(
            neo4j_username or NEO4J_USERNAME,
            neo4j_password or NEO4J_PASSWORD,
        )
        self.llm_client = OpenAI(
            base_url=llm_base_url or LLM_BASE_URL,
            api_key=llm_api_key or LLM_API_KEY,
        )
        self.llm_model = llm_model or LLM_MODEL

    def _query_neo4j(self, cypher):
        body = {"statement": cypher}
        resp = requests.post(
            self.neo4j_url,
            json=body,
            auth=self.neo4j_auth,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
        result_data = data.get("data", {})
        fields = result_data.get("fields", [])
        values = result_data.get("values", [])
        return [dict(zip(fields, row)) for row in values]

    def _llm_chat(self, system_prompt, user_prompt):
        stream = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            stream=True,
            extra_body={
                "enable_thinking": False,
                "top_p": 0.8,
                "top_k": 20,
                "min_p": 0
            },
        )
        content = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
        return content.strip()

    def ask(self, question):
        cypher = self._llm_chat(
            "You are a Cypher expert. Output ONLY the query, no other text.",
            CYPHER_GENERATION_PROMPT.format(schema=GRAPH_SCHEMA, examples=CYPHER_EXAMPLES, question=question),
        )
        cypher = cypher.strip().removeprefix("```cypher").removeprefix("```").removesuffix("```").strip()

        try:
            results = self._query_neo4j(cypher)
        except Exception as e:
            return {
                "question": question,
                "cypher": cypher,
                "error": str(e),
                "answer": None,
            }

        answer = self._llm_chat(
            "You are a research assistant. Answer based on the data provided.",
            ANSWER_PROMPT.format(
                schema=GRAPH_SCHEMA,
                question=question,
                cypher=cypher,
                results=json.dumps(results, indent=2, ensure_ascii=False),
            ),
        )

        return {
            "question": question,
            "cypher": cypher,
            "results": results,
            "answer": answer,
        }

    def ask_baseline(self, question):
        stream = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": question}],
            temperature=0.7,
            stream=True,
            extra_body={
                "enable_thinking": False,
                "top_p": 0.8,
                "top_k": 20,
                "min_p": 0
            },
        )
        content = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
        return {
            "question": question,
            "answer": content.strip(),
        }

    def ask_augmented(self, question):
        return self.ask(question)


def run_interactive(rag):
    print("GraphRAG QA — type 'exit' to quit\n")
    while True:
        try:
            question = input(">>> ")
            if question.lower() in ("exit", "quit"):
                break
            if not question.strip():
                continue

            print("[Baseline]")
            baseline = rag.ask_baseline(question)
            print(f"  {baseline['answer']}\n")

            print("[Augmented (KG + LLM)]")
            augmented = rag.ask_augmented(question)
            print(f"  Cypher: {augmented['cypher']}")
            if augmented.get("error"):
                print(f"  Error: {augmented['error']}")
            else:
                print(f"  Results: {json.dumps(augmented['results'], ensure_ascii=False)[:500]}")
            print(f"  Answer: {augmented['answer']}\n")
        except KeyboardInterrupt:
            print()
            break
        except Exception as e:
            print(f"Error: {e}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["interactive", "single", "baseline", "augmented"],
                        default="single")
    parser.add_argument("--question", type=str, default="List all papers by massimo melucci")
    args = parser.parse_args()

    rag = GraphRAG()

    if args.mode == "interactive":
        run_interactive(rag)
    elif args.mode == "baseline":
        result = rag.ask_baseline(args.question)
        print(f"Question: {result['question']}")
        print(f"Answer: {result['answer']}")
    elif args.mode == "augmented":
        result = rag.ask_augmented(args.question)
        print(f"Question: {result['question']}")
        print(f"Cypher: {result['cypher']}")
        print(f"Answer: {result['answer']}")
    else:
        result = rag.ask(args.question)
        print(f"Question: {result['question']}")
        print(f"Cypher: {result['cypher']}")
        print(f"Results: {json.dumps(result['results'], ensure_ascii=False)[:800]}")
        print(f"Answer: {result['answer']}")


if __name__ == "__main__":
    main()
