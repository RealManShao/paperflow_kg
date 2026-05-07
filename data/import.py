import csv
import os
from neo4j import GraphDatabase

# ================= 配置区域 =================
NEO4J_URI = "neo4j://127.0.0.1:7687"  # 如果是 AuraDB，改为 neo4j+s://...
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "12345678"  # 请修改为你的密码
NEO4J_DATABASE = "test1" 

# 文件路径 (请确保这些文件在 data/processed/ 目录下，且已转换为 csv格式)
ENTITY_FILE = "data/processed/entities.csv"
RELATION_FILE = "data/processed/relations.csv"

# ================= 核心类 =================
class KGBuilder:
    def __init__(self, uri, user, password, database_name):
        self.driver = GraphDatabase.driver(uri, auth=(user, password), database=database_name)

    def close(self):
        self.driver.close()

    def execute_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return list(result)

    def create_constraints_and_indexes(self):
        """
        创建唯一约束和索引。
        1. 保证实体ID唯一，防止重复导入。
        2. 加速基于ID的查找。
        """
        print("🔧 正在创建约束和索引...")
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.type)",
            "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name)"
        ]
        for q in queries:
            self.execute_query(q)
        print("✅ 约束与索引创建完成。")

    def import_entities(self, file_path):
        """
        使用 LOAD CSV 批量导入节点。
        注意：这里我们将所有实体统一标记为 :Entity 标签，
        并通过 type 属性区分 Paper, Author, Conference 等。
        这样设计比动态标签更稳定，便于后续统一查询。
        """
        print(f"📥 正在从 {file_path} 导入实体...")
        
        # Cypher 语句：加载 CSV，MERGE 节点（存在则忽略，不存在则创建）
        cypher = """
        LOAD CSV WITH HEADERS FROM $file_url AS row
        MERGE (n:Entity {id: row.id})
        ON CREATE SET 
            n.name = row.name, 
            n.type = row.type
        ON MATCH SET 
            n.name = row.name, 
            n.type = row.type
        RETURN count(*) as created_count
        """
        
        # Neo4j LOAD CSV 需要 file:/// 前缀，指向 import 目录
        # 如果是本地 Desktop，默认 import 目录在 Neo4j 安装目录下
        # 为了方便，我们这里使用 apoc 或者简单起见，建议将 csv 放在 Neo4j 的 import 文件夹
        # 或者使用 Python 逐行插入作为备选方案（如果数据量不大，<10万条）
        
        # 【备选方案：Python 逐行插入，适合初学者，无需配置 import 目录】
        count = 0
        batch_size = 1000
        batch_data = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                batch_data.append(row)
                if len(batch_data) >= batch_size:
                    self._insert_entity_batch(batch_data)
                    count += len(batch_data)
                    print(f"   ... 已导入 {count} 个实体")
                    batch_data = []
            
            if batch_data:
                self._insert_entity_batch(batch_data)
                count += len(batch_data)
                
        print(f"✅ 实体导入完成，共 {count} 个节点。")

    def _insert_entity_batch(self, batch):
        """批量插入实体"""
        query = """
        UNWIND $batch AS row
        MERGE (n:Entity {id: row.id})
        SET n.name = row.name, n.type = row.type
        """
        self.execute_query(query, {"batch": batch})

    def import_relations(self, file_path):
        """
        批量导入关系。
        由于关系类型动态变化（author_write_paper, paper_cite_paper 等），
        我们需要使用 APOC 库或者动态 Cypher。
        为了简化，这里使用 Python 循环调用，针对每种关系类型优化。
        """
        print(f"🔗 正在从 {file_path} 导入关系...")
        
        # 第一步：读取所有关系，按类型分组
        relations_by_type = {}
        total_count = 0
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=',') # 假设是 tab 分隔，如果是逗号请改为 ','
            # 如果文件有表头，加 next(reader)
            for row in reader:
                start_id, rel_type, end_id = row
                # 清理关系类型，使其符合 Neo4j 命名规范（大写，无空格）
                # 例如: author_write_paper -> WRITES
                clean_rel_type = self._clean_rel_type(rel_type)
                
                if clean_rel_type not in relations_by_type:
                    relations_by_type[clean_rel_type] = []
                relations_by_type[clean_rel_type].append((start_id, end_id))
                total_count += 1

        # 第二步：按类型批量导入
        for rel_type, pairs in relations_by_type.items():
            print(f"   ... 处理关系类型: {rel_type} ({len(pairs)} 条)")
            self._insert_relation_batch(rel_type, pairs)
            
        print(f"✅ 关系导入完成，共 {total_count} 条关系。")

    def _clean_rel_type(self, raw_type):
        """将下划线命名转换为大驼峰命名，适合作为关系类型"""
        # 示例: author_write_paper -> AUTHOR_WRITE_PAPER (Neo4j 关系类型通常大写)
        return raw_type.upper().replace(" ", "_")

    def _insert_relation_batch(self, rel_type, pairs):
        """批量插入特定类型的关系"""
        # 使用 UNWIND 批量处理
        query = f"""
        UNWIND $pairs AS pair
        MATCH (start:Entity {{id: pair[0]}})
        MATCH (end:Entity {{id: pair[1]}})
        MERGE (start)-[r:{rel_type}]->(end)
        """
        # 注意：f-string 注入关系类型是安全的，因为 rel_type 来自我们自己的清洗逻辑
        self.execute_query(query, {"pairs": pairs})

    def get_stats(self):
        """获取图谱统计信息，用于报告"""
        print("\n📊 图谱统计信息:")
        
        # 1. 节点总数及类型分布
        node_stats = self.execute_query("""
            MATCH (n:Entity)
            RETURN n.type AS type, count(*) AS count
            ORDER BY count DESC
        """)
        print("   [节点分布]")
        for record in node_stats:
            print(f"      {record['type']}: {record['count']}")
            
        # 2. 关系总数及类型分布
        rel_stats = self.execute_query("""
            MATCH ()-[r]->()
            RETURN type(r) AS rel_type, count(*) AS count
            ORDER BY count DESC
        """)
        print("   [关系分布]")
        for record in rel_stats:
            print(f"      {record['rel_type']}: {record['count']}")
            
        return node_stats, rel_stats

# ================= 执行入口 =================
if __name__ == "__main__":
    # 初始化构建器
    builder = KGBuilder(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)
    
    try:
        # 1. 创建索引
        builder.create_constraints_and_indexes()
        
        # 2. 导入实体
        # 请确保 entities.csv 存在，如果没有，请先运行下方的转换脚本
        if os.path.exists(ENTITY_FILE):
            builder.import_entities(ENTITY_FILE)
        else:
            print(f"⚠️ 警告: 未找到 {ENTITY_FILE}，请检查路径或先运行数据转换脚本。")
            
        # 3. 导入关系
        if os.path.exists(RELATION_FILE):
            builder.import_relations(RELATION_FILE)
        else:
            print(f"⚠️ 警告: 未找到 {RELATION_FILE}，请检查路径。")
            
        # 4. 输出统计
        builder.get_stats()
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
    finally:
        builder.close()