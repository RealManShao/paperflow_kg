# src/build_kg.py - Neo4j导入核心函数
from neo4j import GraphDatabase
import pandas as pd

class KGBuilder:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def import_papers(self, papers_df):
        """导入论文节点（带错误处理）"""
        with self.driver.session() as session:
            for _, row in papers_df.iterrows():
                try:
                    session.run("""
                        MERGE (p:Paper {paper_id: $pid})
                        SET p.title = $title,
                            p.year = $year,
                            p.keywords = $keywords
                    """, {
                        "pid": row["paper_id"],
                        "title": row["title"],
                        "year": row["year"],
                        "keywords": row.get("keywords", "")
                    })
                except Exception as e:
                    print(f"❌ 导入论文 {row['title']} 失败: {e}")
    
    def import_relations(self, triples_df):
        """导入关系（支持多种类型）"""
        with self.driver.session() as session:
            for _, row in triples_df.iterrows():
                session.run(f"""
                    MATCH (source:{row['source_type']} {{{row['source_key']}: $source_val}})
                    MATCH (target:{row['target_type']} {{{row['target_key']}: $target_val}})
                    MERGE (source)-[r:{row['relation_type']}]->(target)
                    {'SET r.' + ' = $'.join(row.get('rel_props', {}).keys()) + ' = $' if row.get('rel_props') else ''}
                """, {
                    "source_val": row["source_val"],
                    "target_val": row["target_val"],
                    **row.get("rel_props", {})
                })
    
    def get_stats(self):
        """生成图谱质量报告（课程报告直接用）"""
        with self.driver.session() as session:
            return session.run("""
                MATCH (n)
                WITH labels(n) AS labels, count(*) AS count
                RETURN labels, count
                UNION
                MATCH ()-[r]->()
                WITH type(r) AS rel_type, count(*) AS count
                RETURN rel_type, count
            """).data()

# 使用示例
if __name__ == "__main__":
    builder = KGBuilder("bolt://localhost:7687", "neo4j", "your_password")
    
    # 导入数据（假设已清洗为DataFrame）
    papers = pd.read_csv("data/processed/papers.csv")
    triples = pd.read_csv("data/processed/triples.csv")
    
    builder.import_papers(papers)
    builder.import_relations(triples)
    
    # 输出质量报告
    print("📊 图谱统计:", builder.get_stats())
    builder.close()