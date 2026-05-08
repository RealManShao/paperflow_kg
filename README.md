
# 领域知识图谱构建、推理与大模型增强系统

## 1. 项目简介

本项目旨在构建一个基于学术文献领域的知识图谱（KG），并结合大语言模型（LLM）实现增强的智能问答与推理系统。针对大模型在事实准确性、可追溯性及复杂多跳推理方面的不足，本系统通过以下三个核心模块提供解决方案：

1. **知识图谱构建**：从清洗后的学术数据中抽取实体（论文、作者、会议、领域等）与关系，存储于 Neo4j 图数据库中，形成结构化的领域知识库。
2. **知识推理引擎**：实现基于路径搜索（BFS/Shortest Path）的推理算法，支持多跳关系查询与证据链发现。
3. **LLM 增强问答 (GraphRAG)**：采用“检索-生成”架构，先从图谱中检索相关子图与推理路径作为证据，再注入 LLM Prompt，显著提升回答的准确性、可解释性并减少幻觉。

本项目满足课程作业要求，包含完整的代码实现、实验对比分析及可视化演示原型。

---

## 2. 代码架构

项目遵循模块化设计原则，目录结构如下：

```text
project/
├── README.md                 # 项目说明文档
├── requirements.txt          # Python 依赖包列表
├── data/
│   ├── raw/                  # 原始数据文件 (entities.csv, relations.csv)
│   └── processed/            # 预处理后的数据
├── src/
│   ├── build_kg.py           # 图谱构建模块：数据导入、Schema创建、约束建立
│   ├── reasoning.py          # 推理模块：路径搜索、关系预测算法实现
│   ├── graph_retrieval.py    # 图谱检索模块：子图提取、邻居节点查询
│   ├── llm_qa.py             # LLM 问答模块：Prompt 构造、双通道（Baseline vs Augmented）问答逻辑
│   └── evaluate.py           # 评估模块：准确率计算、幻觉检测、指标统计
├── prompts/
│   └── kg_augmented_prompt.txt # LLM 增强提示词模板
├── results/
│   ├── cases.md              # 测试用例与案例分析
│   └── metrics.json          # 实验量化指标结果
├── report.pdf                # 课程报告
└── slides.pdf                # 课堂展示 PPT
```

### 核心模块说明

| 模块 | 文件 | 功能描述 |
| :--- | :--- | :--- |
| **KG Builder** | `src/build_kg.py` | 连接 Neo4j，读取 CSV 数据，动态映射实体标签（Paper, Author 等），批量导入节点与关系，并创建唯一约束索引。 |
| **Reasoner** | `src/reasoning.py` | 基于 NetworkX 或 Cypher 实现最短路径查找 (`shortest_path`)，用于发现实体间的间接关联。 |
| **Retriever** | `src/graph_retrieval.py` | 根据用户问题中的实体，从 Neo4j 中检索 k-hop 子图及相关的推理路径。 |
| **LLM QA** | `src/llm_qa.py` | 封装 LLM 接口（支持 Ollama/OpenAI）。实现 `answer_baseline`（纯 LLM）和 `answer_augmented`（KG+LLM）两种模式。 |
| **Evaluator** | `src/evaluate.py` | 运行预设测试集，对比两种模式的回答，计算准确率、证据覆盖率等指标。 |

---

## 3. 使用方法

### 3.1 环境准备

1. **安装 Python 依赖**：
   ```bash
   pip install -r requirements.txt
   ```
   *主要依赖：`neo4j`, `networkx`, `pandas`, `openai` (或 `ollama`)*

2. **启动 Neo4j 数据库**：
   - 推荐使用 **Neo4j Desktop** 或 **Docker**。
   - 确保数据库服务正在运行，默认端口为 `7687` (Bolt) 和 `7474` (Browser)。
   - 记录用户名（默认 `neo4j`）和密码。

### 3.2 数据准备
数据集采用Microsoft KG20C （[arxiv](https://arxiv.org/pdf/2512.21799)）原始数据为TXT格式，经过清洗后得到CSV格式的数据文件。

清洗好的数据文件在 `data/processed/` 目录：
- `entities.csv`: 格式为 `id,name,type`
- `relations.csv`: 格式为 `start_id,rel_type,end_id`

### 3.3 构建知识图谱

运行构建脚本，将数据导入 Neo4j：

```bash
python src/build_kg.py
```

*脚本执行完成后，会在控制台输出节点和关系的统计信息，并在 Neo4j Browser 中可查看可视化图谱。*

### 3.4 配置 LLM

在 `src/llm_qa.py` 或环境变量中配置 LLM 密钥或本地模型地址：

```python
# 示例：使用 Ollama 本地模型
OLLAMA_MODEL = "llama3:8b"
OLLAMA_BASE_URL = "http://localhost:11434"

# 或者使用 OpenAI API
OPENAI_API_KEY = "sk-..."
```

### 3.5 运行问答与评估

#### 方式一：交互式问答演示
```bash
python src/llm_qa.py --mode interactive
```
输入问题，系统将分别展示“基线回答”和“图谱增强回答”，并高亮显示使用的图谱证据。

#### 方式二：批量实验评估
```bash
python src/evaluate.py
```
系统将自动读取 `results/cases.md` 中的测试问题，执行对比实验，并将量化指标保存至 `results/metrics.json`。

### 3.6 查看结果

- **量化指标**：打开 `results/metrics.json` 查看准确率提升、幻觉减少比例等数据。
- **案例分析**：打开 `results/cases.md` 查看具体问题的详细对比分析。
- **可视化**：访问 `http://localhost:7474` 在 Neo4j Browser 中探索图谱结构。

---

## 4. 注意事项

1. **数据唯一性**：确保 `entities.csv` 中的 ID 全局唯一，否则导入时会因唯一约束冲突报错。
2. **关系类型映射**：`build_kg.py` 中预定义了关系类型映射表，若新增关系类型，请在 `RELATION_MAPPING` 字典中添加对应项。
3. **LLM 稳定性**：若使用本地小模型，建议增加 Temperature=0 以确保输出稳定性；若使用 API，请注意调用频率限制。
4. **性能优化**：对于大规模图谱（>10k 节点），建议在 `reasoning.py` 中使用 Neo4j GDS 库替代内存图计算以提升速度。