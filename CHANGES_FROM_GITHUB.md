# 相比 GitHub 原版的改动与意义（paperflow_kg）

本文档总结当前工作区代码相对“最初从 GitHub clone 下来的原始版本”的全部关键改动，并解释每类改动的意义与对使用方式的影响。

> 目标导向：让项目**可复现、可配置、安全**，并提供一个可用的**前端交互界面**与最小评估闭环。

## 1. 改动总览

**核心变化**

- 移除所有硬编码的 Neo4j Aura / LLM 密钥与地址，改为 `.env/环境变量` 驱动
- 新增 Streamlit 单页前端（4 个页签：KG 构建 / 检索 / 推理 / 问答）
- 补齐 `prompts/`、`results/`、`src/evaluate.py`，形成“用例 → 评估 → 指标输出”的最小闭环
- README 补全从零跑通教程 + 前端使用说明 + 常见报错排查

**变更文件清单**

- 修改：`.gitignore`、`README.md`、`requirements.txt`
- 修改：`src/build_kg.py`、`src/graph_retrieval.py`、`src/reasoning.py`、`src/llm_qa.py`、`tests/test_query_api.py`
- 新增：`.env.example`、`app.py`、`src/evaluate.py`、`prompts/kg_augmented_prompt.txt`、`results/cases.md`

## 2. 安全性与可复现性：去硬编码密钥

### 2.1 Neo4j 配置改为环境变量

涉及文件：`src/build_kg.py`、`src/graph_retrieval.py`、`src/reasoning.py`、`src/llm_qa.py`、`tests/test_query_api.py`

**原版问题**

- 在代码内写死 Neo4j Aura 的 URL/用户名/密码，会导致：
  - 密钥泄漏风险（仓库一旦公开/转发就暴露）
  - 其他人无法复现（除非恰好能访问同一套 Neo4j 实例）

**当前改动**

- 统一从 `.env/环境变量`读取：
  - Bolt（用于 KG 导入）：`NEO4J_URI`、`NEO4J_DATABASE`、`NEO4J_USERNAME`、`NEO4J_PASSWORD`
  - HTTP Query API v2（用于检索/推理/GraphRAG）：`NEO4J_QUERY_API_URL`、`NEO4J_USERNAME`、`NEO4J_PASSWORD`
- 对缺失配置给出明确报错/跳过逻辑（避免“静默失败”或连到不该连的默认库）

**意义**

- 安全：仓库本身不包含任何真实凭据
- 可复现：任何人只需填写自己的 Neo4j 配置即可运行
- 可维护：配置集中，减少“改代码换环境”的摩擦

### 2.2 LLM 改为 OpenAI-compatible 且支持别名

涉及文件：`src/llm_qa.py`、`app.py`、`README.md`

**当前配置变量**

- `LLM_BASE_URL`：OpenAI-compatible base url（默认 `https://api.openai.com/v1`）
- `LLM_API_KEY`：API Key（必填）
- `LLM_MODEL`：模型名（默认 `gpt-4.1-mini`）

**兼容别名（便于复用你已有的环境变量命名）**

- Base URL：`DEEPSEEK_API_BASE`、`OPENAI_BASE_URL`、`OPENAI_API_BASE`
- Key：`DASHSCOPE_API_KEY`、`OPENAI_API_KEY`、`DEEPSEEK_API_KEY`

**意义**

- 保持对多家“OpenAI-compatible”服务的兼容（例如 DashScope compatible-mode）
- 避免把 Key 写在代码里，降低泄漏风险

## 3. SSL 校验行为：从强制关闭到可配置

涉及文件：`src/llm_qa.py`、`src/graph_retrieval.py`、`src/reasoning.py`、`tests/test_query_api.py`

**原版问题**

- 对 Neo4j Query API 请求使用 `verify=False`（等同于禁用 HTTPS 证书校验）

**当前改动**

- 新增 `NEO4J_VERIFY_SSL`（默认 `true`），统一传给 `requests` 的 `verify=...`

**意义**

- 默认更安全；仅在公司代理/抓包导致证书异常时，才建议设置为 `false`

## 4. 新增 Streamlit 前端：交互式复现与演示

涉及文件：`app.py`（新增）、`requirements.txt`、`README.md`

**新增能力**

- 单页 Streamlit 应用，4 个页签：
  1) **KG 构建**：从 `entities.csv/relations.csv` 导入 Neo4j（Bolt）
  2) **图谱检索**：按名称模糊搜索实体，查看论文详情或 k-hop 邻居
  3) **推理**：输入 source/target 实体 id，计算最短路径并展示证据链
  4) **问答**：同一问题对比 Baseline（纯 LLM） vs Augmented（KG+LLM，展示 Cypher 与结果）
- 侧边栏展示配置状态（对密码做 mask）并提供“Neo4j Query API 连通性自检”

**意义**

- 让项目从“脚本集合”变成“可演示、可交互”的应用
- 更适合课程展示/答辩：不用反复敲命令即可演示完整链路

## 5. 补齐评估闭环：用例集 + 指标输出

涉及文件：`src/evaluate.py`（新增）、`results/cases.md`（新增）、`.gitignore`

**新增能力**

- `src/evaluate.py`：读取 `results/cases.md`（每行一个问题）
  - 对每个问题跑 baseline 与 augmented
  - 记录成功率、查询成功率、延迟等指标
  - 输出 `results/metrics.json`

**意义**

- 评估更可重复：用例固定、输出结构固定，便于写报告或回归对比

## 6. Tests：从“默认连作者库”到“配置了才跑”

涉及文件：`tests/test_query_api.py`

**当前改动**

- 增加 `.env` 加载
- 若缺少 `NEO4J_QUERY_API_URL/NEO4J_USERNAME/NEO4J_PASSWORD`，测试直接 `SkipTest`

**意义**

- CI/他人机器不会因为缺 Neo4j 配置而误报失败
- 避免无意间连到仓库里写死的第三方 Neo4j

## 7. 依赖与工程文件

### 7.1 requirements.txt

涉及文件：`requirements.txt`

- 删除：`longchain`（与代码不匹配/拼写不可靠）
- 新增：`streamlit`（前端）与 `python-dotenv`（.env）

### 7.2 .gitignore

涉及文件：`.gitignore`

- 新增忽略：`.env`、`__pycache__/`、`results/metrics.json`

**意义**

- 防止提交密钥与评估生成物，保持仓库干净

## 8. README：从“概述”升级为“可跑通教程 + 前端说明”

涉及文件：`README.md`

**新增/强化内容**

- 快速开始：conda/venv 建环境、装依赖、复制 `.env`、启动 Streamlit
- 统一强调：密钥必须通过 `.env/环境变量` 提供，不在代码中写死
- 前端使用方法简述 + 常见报错排查

**意义**

- 降低复现门槛：按步骤做就能跑，不需要读很多代码

## 9. 使用方式变化（迁移提示）

- 现在**必须**提供 `.env`（或等价环境变量）才能运行 augmented/检索/推理相关功能
- 如果只跑 baseline（纯 LLM），只需配置 LLM 相关变量

建议流程：

1) `cp .env.example .env` 并填写
2) `pip install -r requirements.txt`
3) 启动前端：`python -m streamlit run app.py`
4) 可选：`python src/evaluate.py` 输出 `results/metrics.json`

## 10. 备注：