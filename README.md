
# 领域知识图谱构建、推理与大模型增强系统

## 1. 项目简介

本项目旨在构建一个基于学术文献领域的知识图谱（KG），并结合大语言模型（LLM）实现增强的智能问答与推理系统。针对大模型在事实准确性、可追溯性及复杂多跳推理方面的不足，本系统通过以下三个核心模块提供解决方案：

1. **知识图谱构建**：从清洗后的学术数据中抽取实体（论文、作者、会议、领域等）与关系，存储于 Neo4j 图数据库中，形成结构化的领域知识库。
2. **知识推理引擎**：实现基于路径搜索（BFS/Shortest Path）的推理算法，支持多跳关系查询与证据链发现。
3. **LLM 增强问答 (GraphRAG)**：采用“检索-生成”架构，先从图谱中检索相关子图与推理路径作为证据，再注入 LLM Prompt，显著提升回答的准确性、可解释性并减少幻觉。

---

## 2. 代码架构

项目遵循模块化设计原则，目录结构如下（以仓库当前代码为准）：

```text
paperflow_kg/
├── README.md                 # 项目说明文档
├── requirements.txt          # Python 依赖包列表
├── .env.example              # 环境变量示例（复制为 .env 后填写）
├── app.py                    # Streamlit 前端入口
├── data/
│   ├── raw/                  # 原始数据文件 (entities.csv, relations.csv)
│   └── processed/            # 预处理后的数据
├── src/
│   ├── build_kg.py           # 图谱构建模块：数据导入、Schema创建、约束建立
│   ├── reasoning.py          # 推理模块：路径搜索、关系预测算法实现
│   ├── graph_retrieval.py    # 图谱检索模块：子图提取、邻居节点查询
│   ├── llm_qa.py             # LLM 问答模块：Prompt 构造、双通道（Baseline vs Augmented）问答逻辑
│   └── evaluate.py           # 评估模块：在少量用例上对比 baseline vs augmented
├── prompts/
│   └── kg_augmented_prompt.txt # LLM 增强提示词模板（可选）
└── results/
   ├── cases.md              # 测试用例（每行一个问题）
   └── metrics.json          # 实验量化指标（evaluate 生成）
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

下面给出一套“从零复现到跑通”的推荐流程（不依赖任何本机固定路径）。

### 3.0 快速开始（推荐）

1) 创建并激活虚拟环境（任选其一）

- conda：
   ```bash
   conda create -n paperflow_kg python=3.11 -y
   conda activate paperflow_kg
   ```

- venv：
   ```bash
   python -m venv .venv
   # Linux/Mac
   source .venv/bin/activate
   # Windows (PowerShell)
   # .venv\Scripts\Activate.ps1
   ```

2) 安装依赖

```bash
pip install -r requirements.txt
```

3) 配置 `.env`

```bash
cp .env.example .env
```

按注释填写：Neo4j（Bolt + Query API）与 LLM（OpenAI-compatible）。

4) 启动前端

```bash
python -m streamlit run app.py
```

5) （可选）快速自检

- 只测 LLM（不依赖 Neo4j）：
   ```bash
   python src/llm_qa.py --mode baseline --question "Reply with exactly: OK"
   ```
- 测 Neo4j Query API（需要配置 `NEO4J_QUERY_API_URL` 等）：
   ```bash
   python -m unittest discover -s tests -q
   ```

### 3.1 环境准备

1. **安装 Python 依赖**：
   ```bash
   pip install -r requirements.txt
   ```
   *主要依赖：`neo4j`, `requests`, `openai`, `streamlit`*

2. **启动 Neo4j 数据库**：
   - 推荐 Neo4j Aura（需要同时开通 Bolt 连接 + Query API v2）

3. **配置环境变量**（推荐使用 `.env`）
   - 将 `.env.example` 复制为 `.env` 并填写：
     - `NEO4J_URI`, `NEO4J_DATABASE`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`（用于 `src/build_kg.py`）
     - `NEO4J_QUERY_API_URL`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`（用于查询/推理/GraphRAG）
       - `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`（OpenAI-compatible）
          - 兼容别名：`DEEPSEEK_API_BASE` 可作为 `LLM_BASE_URL`，`DASHSCOPE_API_KEY` 可作为 `LLM_API_KEY`


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

通过环境变量配置（建议写入 `.env`）：

- `LLM_BASE_URL`：OpenAI-compatible 接口地址（默认 `https://api.openai.com/v1`）
- `LLM_API_KEY`：你的 API Key
- `LLM_MODEL`：模型名（默认 `gpt-4.1-mini`，可改为任意兼容模型）

例如使用 DashScope OpenAI-compatible：
- `DEEPSEEK_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`
- `DASHSCOPE_API_KEY=...`
- `LLM_MODEL=qwen3.6-flash`

### 3.5 运行问答与评估

#### 方式一：交互式问答演示
```bash
python src/llm_qa.py --mode interactive
```
输入问题，系统将分别展示“基线回答”和“图谱增强回答”，并高亮显示使用的图谱证据。

#### 方式一（推荐）：前端交互界面（Streamlit）
```bash
python -m streamlit run app.py
```
在浏览器中提供四个页签：`KG 构建 / 图谱检索 / 推理 / 问答`。

**前端使用方法（简要）**

1. 左侧栏会显示当前 `.env`/环境变量读取到的配置（Neo4j/LLM），可点击 **“测试 Neo4j Query API”** 做连通性自检。
2. `KG 构建`：将 `data/processed/entities.csv` 与 `data/processed/relations.csv` 导入 Neo4j（需要配置 Bolt：`NEO4J_URI` 等）。
3. `图谱检索`：按名称模糊搜索实体（可选类型），选择结果后：
   - 如果是 Paper：展示论文详情（作者/引用/会议/领域等）。
   - 其他实体：展示 k-hop 邻居列表。
4. `推理`：输入 `source_id` 和 `target_id`（实体 id），查找最短路径并展示证据链。
5. `问答`：输入问题后可选择运行 `Baseline`（纯 LLM）或 `Augmented`（KG+LLM，会展示生成的 Cypher 与查询结果）。

**常见报错**

- `No module named streamlit`
   - 原因：你运行 `python` 的环境里没装依赖（没激活 conda/venv，或装在了另一个环境）。
   - 处理：重新激活环境后执行 `pip install -r requirements.txt`，并用同一个环境运行 `python -m streamlit ...`。

- `Missing NEO4J_QUERY_API_URL` / `Missing Neo4j credentials`
   - 原因：`.env` 中 Neo4j Query API 配置缺失。
   - 处理：补齐 `NEO4J_QUERY_API_URL / NEO4J_USERNAME / NEO4J_PASSWORD`。

- LLM 401/403
   - 原因：LLM key 或 base_url/model 配置不正确。
   - 处理：检查 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`（或别名 `DEEPSEEK_API_BASE/DASHSCOPE_API_KEY`）。

#### 方式二：批量实验评估
```bash
python src/evaluate.py
```
系统将读取 `results/cases.md` 中的测试问题，执行对比实验，并将量化指标保存至 `results/metrics.json`。

### 3.6 查看结果

- **量化指标**：打开 `results/metrics.json` 查看准确率提升、幻觉减少比例等数据。
- **案例分析**：打开 `results/cases.md` 查看具体问题的详细对比分析。
- **可视化**：访问 `http://localhost:7474` 在 Neo4j Browser 中探索图谱结构。

---

## 4. 注意事项

1. **数据唯一性**：确保 `entities.csv` 中的 ID 全局唯一，否则导入时会因唯一约束冲突报错。
2. **关系类型映射**：`build_kg.py` 中预定义了关系类型映射表，若新增关系类型，请在 `RELATION_MAPPING` 字典中添加对应项。
3. **安全性**：仓库代码不会内置任何真实的 Neo4j/LLM 密钥；请使用环境变量或 `.env` 提供。
