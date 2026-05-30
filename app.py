import os
import sys
import json
from typing import Optional

import streamlit as st
from dotenv import load_dotenv


# Make src/* importable when running `streamlit run app.py`
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

load_dotenv()

# Local imports (from ./src)
from build_kg import KGBuilder  # noqa: E402
from graph_retrieval import GraphRetriever  # noqa: E402
from reasoning import Reasoner  # noqa: E402
from llm_qa import GraphRAG  # noqa: E402


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _masked(value: Optional[str]) -> str:
    if not value:
        return "(missing)"
    if len(value) <= 6:
        return "***"
    return value[:3] + "…" + value[-3:]


def _require(value: Optional[str], message: str) -> bool:
    if value:
        return True
    st.error(message)
    return False


@st.cache_resource
def _get_retriever():
    return GraphRetriever()


@st.cache_resource
def _get_reasoner():
    return Reasoner()


@st.cache_resource
def _get_rag():
    return GraphRAG()


st.set_page_config(page_title="paperflow_kg", layout="wide")

st.title("paperflow_kg — 领域知识图谱 + 推理 + GraphRAG")
st.caption("提示：所有连接信息从环境变量或 .env 读取；侧边栏可查看配置状态与连通性自检。")

with st.sidebar:
    st.header("配置状态")

    st.subheader("Neo4j (HTTP Query API)")
    st.text(f"NEO4J_QUERY_API_URL: {_env('NEO4J_QUERY_API_URL', '(missing)')}")
    st.text(f"NEO4J_USERNAME: {_env('NEO4J_USERNAME', '(missing)')}")
    st.text(f"NEO4J_PASSWORD: {_masked(_env('NEO4J_PASSWORD'))}")
    st.text(f"NEO4J_VERIFY_SSL: {_env('NEO4J_VERIFY_SSL', 'true')}")

    st.subheader("Neo4j (Bolt, for KG build)")
    st.text(f"NEO4J_URI: {_env('NEO4J_URI', 'neo4j://localhost:7687')}")
    st.text(f"NEO4J_DATABASE: {_env('NEO4J_DATABASE', 'neo4j')}")

    st.subheader("LLM")
    effective_base = _env("LLM_BASE_URL") or _env("DEEPSEEK_API_BASE") or "https://api.openai.com/v1"
    st.text(f"LLM_BASE_URL: {effective_base}")
    if _env("DEEPSEEK_API_BASE") and not _env("LLM_BASE_URL"):
        st.caption("Using DEEPSEEK_API_BASE as LLM_BASE_URL alias")
    st.text(f"LLM_MODEL: {_env('LLM_MODEL', 'gpt-4.1-mini')}")
    effective_key = (
        _env("LLM_API_KEY")
        or _env("DASHSCOPE_API_KEY")
        or _env("OPENAI_API_KEY")
        or _env("DEEPSEEK_API_KEY")
    )
    st.text(f"LLM_API_KEY: {_masked(effective_key)}")
    if _env("DASHSCOPE_API_KEY") and not _env("LLM_API_KEY"):
        st.caption("Using DASHSCOPE_API_KEY as LLM_API_KEY alias")

    st.divider()

    if st.button("测试 Neo4j Query API"):
        try:
            retriever = _get_retriever()
            ping = retriever._run("RETURN 1 AS ok")
            st.success(f"Neo4j OK: {ping}")
        except Exception as e:
            st.error(f"Neo4j failed: {e}")


kg_tab, retrieval_tab, reasoning_tab, qa_tab = st.tabs([
    "KG 构建",
    "图谱检索",
    "推理",
    "问答 (Baseline vs KG+LLM)",
])


with kg_tab:
    st.subheader("导入 CSV 到 Neo4j")
    st.write("读取 `data/processed/entities.csv` 与 `data/processed/relations.csv`，创建约束并批量导入。")

    entity_file = st.text_input("entities.csv 路径", value=os.path.join("data", "processed", "entities.csv"))
    relation_file = st.text_input("relations.csv 路径", value=os.path.join("data", "processed", "relations.csv"))

    col1, col2 = st.columns(2)
    with col1:
        do_constraints = st.checkbox("创建唯一约束", value=True)
    with col2:
        show_stats = st.checkbox("导入后输出统计", value=True)

    with st.form("kg_import_form", border=True):
        submitted = st.form_submit_button("开始导入")

    if submitted:
        try:
            uri = _env("NEO4J_URI", "neo4j://localhost:7687")
            user = _env("NEO4J_USERNAME")
            pwd = _env("NEO4J_PASSWORD")
            db = _env("NEO4J_DATABASE", "neo4j")

            if not _require(user, "缺少 Neo4j 凭据：请设置 NEO4J_USERNAME"):
                st.stop()
            if not _require(pwd, "缺少 Neo4j 凭据：请设置 NEO4J_PASSWORD"):
                st.stop()

            missing_files = [p for p in (entity_file, relation_file) if not os.path.exists(p)]
            if missing_files:
                st.error("未找到文件：\n- " + "\n- ".join(missing_files))
                st.stop()

            builder = KGBuilder(uri, user, pwd, db)
            with st.spinner("正在导入（详细日志输出在终端）..."):
                if do_constraints:
                    builder.create_constraints()
                builder.import_entities(entity_file)
                builder.import_relations(relation_file)
                if show_stats:
                    builder.get_stats()
            builder.close()
            st.success("导入完成")
        except Exception as e:
            st.error(str(e))


with retrieval_tab:
    st.subheader("按名称检索实体，并查看邻居/论文详情")

    try:
        retriever = _get_retriever()
    except Exception as e:
        st.error(f"GraphRetriever 初始化失败: {e}")
        retriever = None

    with st.form("retrieval_form", border=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            query = st.text_input("实体名称包含", value=st.session_state.get("retrieval_query", "algorithm"))
        with col2:
            label = st.selectbox(
                "实体类型（可选）",
                options=["(Any)", "Paper", "Author", "Conference", "Domain", "Affiliation"],
                index=0,
            )
        with col3:
            limit = st.number_input("返回条数", min_value=1, max_value=20, value=5)
        submit_search = st.form_submit_button("搜索")

    if retriever and submit_search:
        try:
            st.session_state["retrieval_query"] = query
            label_value = None if label == "(Any)" else label
            hits = retriever.find_entity_by_name(query, label=label_value, limit=int(limit))
            st.session_state["retrieval_hits"] = hits
        except Exception as e:
            st.error(str(e))

    hits = st.session_state.get("retrieval_hits", [])
    if hits:
        st.write(f"命中 {len(hits)} 条")
        st.dataframe(hits, use_container_width=True)

        options = [f"{h['type']} | {h['name']} | {h['id']}" for h in hits]
        default_selected = st.session_state.get("retrieval_selected", options[0])
        selected = st.selectbox("选择一条查看详情", options=options, index=options.index(default_selected) if default_selected in options else 0)
        st.session_state["retrieval_selected"] = selected
        selected_id = selected.split(" | ")[-1]

        try:
            entity = retriever.get_entity_by_id(selected_id)
            if not entity:
                st.warning("实体不存在或不可访问")
            else:
                if entity.get("type") == "Paper":
                    st.markdown("#### 论文详情")
                    details = retriever.get_paper_details(selected_id)
                    st.json(details)
                else:
                    st.markdown("#### 实体信息")
                    st.json(entity)

                    st.markdown("#### k-hop 邻居")
                    colk1, colk2 = st.columns([1, 1])
                    with colk1:
                        k = st.slider("k", min_value=1, max_value=3, value=1)
                    with colk2:
                        direction = st.selectbox("方向", options=["both", "outgoing", "incoming"], index=0)
                    neighbors = retriever.get_k_hop_neighbors(selected_id, k=int(k), direction=direction)
                    st.dataframe(neighbors, use_container_width=True)
        except Exception as e:
            st.error(str(e))
    else:
        st.info("先在上面搜索一个实体。")


with reasoning_tab:
    st.subheader("最短路径推理（证据链）")

    try:
        reasoner = _get_reasoner()
    except Exception as e:
        st.error(f"Reasoner 初始化失败: {e}")
        reasoner = None

    with st.form("reasoning_form", border=True):
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            source_id = st.text_input("source_id", value=st.session_state.get("source_id", ""))
        with col2:
            target_id = st.text_input("target_id", value=st.session_state.get("target_id", ""))
        with col3:
            max_hops = st.number_input("max_hops", min_value=1, max_value=10, value=int(st.session_state.get("max_hops", 5)))

        submit_reason = st.form_submit_button("查找最短路径")

    if reasoner and submit_reason:
        st.session_state["source_id"] = source_id
        st.session_state["target_id"] = target_id
        st.session_state["max_hops"] = int(max_hops)

        if not source_id.strip() or not target_id.strip():
            st.warning("请填写 source_id 和 target_id")
        else:
            try:
                chain = reasoner.find_shortest_path(source_id.strip(), target_id.strip(), max_hops=int(max_hops))
                st.session_state["reasoning_chain"] = chain
            except Exception as e:
                st.error(str(e))

    chain = st.session_state.get("reasoning_chain")
    if chain is not None:
        if not chain:
            st.info("未找到路径")
        else:
            st.markdown(reasoner.format_reasoning_chain(chain), unsafe_allow_html=False)
            with st.expander("查看 JSON", expanded=False):
                st.json(chain)


with qa_tab:
    st.subheader("GraphRAG：Baseline vs KG+LLM")

    with st.form("qa_form", border=True):
        question = st.text_area(
            "问题",
            value=st.session_state.get("qa_question", "List all papers by massimo melucci"),
            height=100,
        )
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            run_baseline = st.checkbox("Baseline", value=True)
        with col2:
            run_augmented = st.checkbox("Augmented", value=True)
        submitted = st.form_submit_button("开始问答")

    if submitted:
        st.session_state["qa_question"] = question
        if not question.strip():
            st.warning("请输入问题")
            st.stop()

        try:
            rag = _get_rag()
        except Exception as e:
            st.error(f"GraphRAG 初始化失败: {e}")
            st.stop()

        if run_baseline:
            with st.spinner("Baseline 生成中..."):
                st.session_state["baseline"] = rag.ask_baseline(question)

        if run_augmented:
            with st.spinner("Augmented 生成中（生成 Cypher + 查询 + 回答）..."):
                st.session_state["augmented"] = rag.ask_augmented(question)

    baseline = st.session_state.get("baseline")
    augmented = st.session_state.get("augmented")

    colL, colR = st.columns(2)
    with colL:
        st.markdown("### Baseline")
        if baseline:
            st.write(baseline.get("answer", ""))
        else:
            st.info("未运行")

    with colR:
        st.markdown("### Augmented")
        if augmented:
            cypher = augmented.get("cypher", "")
            if cypher:
                st.code(cypher, language="cypher")
            if augmented.get("error"):
                st.error(augmented["error"])
            else:
                with st.expander("查看 Query Results", expanded=False):
                    st.json(augmented.get("results", []))
            st.markdown("#### Answer")
            st.write(augmented.get("answer", ""))
        else:
            st.info("未运行")

    st.markdown("---")
    st.caption("提示：若 LLM 或 Neo4j 连接失败，请检查 .env 或环境变量配置。")
