import csv
import os
from neo4j import GraphDatabase

from dotenv import load_dotenv

# ================= 配置区域 =================
# 说明：为了便于复现与安全，连接信息全部从环境变量读取。
# 推荐在项目根目录创建 .env（可参考 .env.example）。
load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
# 文件路径
ENTITY_FILE = "data/processed/entities.csv"
RELATION_FILE = "data/processed/relations.csv"

# 实体类型映射 (第3列的值 -> Neo4j Label)
# 注意：Neo4j Label 通常首字母大写
TYPE_MAPPING = {
    "paper": "Paper",
    "author": "Author",
    "domain": "Domain",
    "conference": "Conference",
    "affiliation": "Affiliation",
    # 如果有其他类型，在此添加，例如: "journal": "Journal"
}

# 关系类型映射 (原始关系名 -> 标准化关系名)
# 这有助于在报告中展示规范的 Schema
RELATION_MAPPING = {
    "author_in_affiliation": "BELONGS_TO_AFFILIATION",
    "author_write_paper": "WRITES",
    "paper_cite_paper": "CITES",
    "paper_in_domain": "BELONGS_TO_DOMAIN",
    "paper_in_venue": "PUBLISHED_IN"
}

class KGBuilder:
    def __init__(self, uri, user, password, database_name):
        if not user or not password:
            raise ValueError(
                "Missing Neo4j credentials. Set NEO4J_USERNAME and NEO4J_PASSWORD in your environment (or .env)."
            )
        self.driver = GraphDatabase.driver(uri, auth=(user, password), database=database_name)

    def close(self):
        self.driver.close()

    def execute_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return list(result)

    def create_constraints(self):
        """
        为每种实体类型创建唯一约束，确保 ID 唯一性并加速查找。
        这是高质量图谱工程的体现。
        """
        print("🔧 正在创建唯一约束...")
        labels = set(TYPE_MAPPING.values())
        for label in labels:
            # 例如: CREATE CONSTRAINT FOR (p:Paper) REQUIRE p.id IS UNIQUE
            query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
            try:
                self.execute_query(query)
                print(f"   ✅ 约束创建: {label}")
            except Exception as e:
                print(f"   ⚠️ 约束创建失败 {label}: {e}")

    def import_entities(self, file_path):
        """
        读取 entities.csv，根据第3列动态分配 Label 并导入。
        """
        print(f"📥 正在从 {file_path} 导入实体...")
        
        # 按类型分组数据，以便批量插入同一类型的节点
        batches = {label: [] for label in TYPE_MAPPING.values()}
        count = 0
        
        # 假设 CSV 没有表头，如果有表头请添加 skipinitialspace=True 或 next(reader)
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # 如果第一行是表头 id,name,type，请取消下面这行的注释
            next(reader) 
            
            for row in reader:
                if len(row) < 3: continue
                
                eid = row[0].strip()
                name = row[1].strip()
                raw_type = row[2].strip().lower()
                
                # 获取对应的 Neo4j Label
                label = TYPE_MAPPING.get(raw_type)
                if label:
                    batches[label].append({"id": eid, "name": name})
                    count += 1
                else:
                    print(f"   ⚠️ 未知实体类型: {raw_type} (ID: {eid})")

        # 批量导入每种类型的节点
        for label, data_list in batches.items():
            if not data_list: continue
            
            # 分批处理，避免单次事务过大
            batch_size = 500
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i+batch_size]
                self._insert_nodes_batch(label, batch)
            
            print(f"   ✅ 导入 {label}: {len(data_list)} 个节点")
            
        print(f"✅ 实体导入完成，共 {count} 个节点。")

    def _insert_nodes_batch(self, label, batch):
        """
        使用 UNWIND 批量插入特定 Label 的节点
        """
        query = f"""
        UNWIND $batch AS row
        MERGE (n:{label} {{id: row.id}})
        SET n.name = row.name
        """
        self.execute_query(query, {"batch": batch})

    def import_relations(self, file_path):
        """
        读取 relations.csv，根据映射表标准化关系类型，并建立连接。
        """
        print(f"🔗 正在从 {file_path} 导入关系...")
        
        # 按关系类型分组
        rel_batches = {}
        total_count = 0
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=',')
            # 如果有表头，请 next(reader)
            
            for row in reader:
                if len(row) != 3: continue
                
                start_id = row[0].strip()
                raw_rel = row[1].strip()
                end_id = row[2].strip()
                
                # 标准化关系类型
                std_rel = RELATION_MAPPING.get(raw_rel, raw_rel.upper().replace(" ", "_"))
                
                if std_rel not in rel_batches:
                    rel_batches[std_rel] = []
                rel_batches[std_rel].append({"start": start_id, "end": end_id})
                total_count += 1

        # 批量导入每种类型的关系
        for rel_type, pairs in rel_batches.items():
            print(f"   ... 处理关系: {rel_type} ({len(pairs)} 条)")
            self._insert_relations_batch(rel_type, pairs)
            
        print(f"✅ 关系导入完成，共 {total_count} 条关系。")

    def _insert_relations_batch(self, rel_type, pairs):
        """
        批量插入关系。
        注意：这里假设起始节点和结束节点已经存在。
        为了通用性，我们匹配所有可能的 Label，或者你可以优化为只匹配特定 Label。
        由于我们已经为每个 ID 创建了唯一约束，直接 MATCH id 即可。
        """
        query = f"""
        UNWIND $pairs AS pair
        MATCH (start {{id: pair.start}})
        MATCH (end {{id: pair.end}})
        MERGE (start)-[r:{rel_type}]->(end)
        """
        # 注意：上面的 MATCH (start {id: ...}) 会扫描所有标签。
        # 性能优化建议：如果数据量大，可以知道 start 和 end 的具体标签。
        # 但在课程作业规模下（<10k节点），这种写法最简单且有效。
        self.execute_query(query, {"pairs": pairs})

    def get_stats(self):
        """生成图谱统计报告"""
        print("\n📊 === 图谱质量分析报告 ===")
        
        # 1. 节点统计
        node_stats = self.execute_query("""
            MATCH (n)
            RETURN labels(n)[0] AS type, count(*) AS count
            ORDER BY count DESC
        """)
        print("   [节点分布]")
        total_nodes = 0
        for record in node_stats:
            print(f"      {record['type']}: {record['count']}")
            total_nodes += record['count']
        print(f"      总节点数: {total_nodes}")
            
        # 2. 关系统计
        rel_stats = self.execute_query("""
            MATCH ()-[r]->()
            RETURN type(r) AS rel_type, count(*) AS count
            ORDER BY count DESC
        """)
        print("   [关系分布]")
        total_rels = 0
        for record in rel_stats:
            print(f"      {record['rel_type']}: {record['count']}")
            total_rels += record['count']
        print(f"      总关系数: {total_rels}")
        
        return total_nodes, total_rels

# ================= 执行入口 =================
if __name__ == "__main__":
    builder = KGBuilder(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
    
    try:
        # 1. 创建约束
        builder.create_constraints()
        
        # 2. 导入实体
        if os.path.exists(ENTITY_FILE):
            builder.import_entities(ENTITY_FILE)
        else:
            print(f"❌ 错误: 未找到 {ENTITY_FILE}")
            
        # 3. 导入关系
        if os.path.exists(RELATION_FILE):
            builder.import_relations(RELATION_FILE)
        else:
            print(f"❌ 错误: 未找到 {RELATION_FILE}")
            
        # 4. 统计与验证
        builder.get_stats()
        
    except Exception as e:
        print(f"❌ 发生严重错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        builder.close()