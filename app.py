"""
演示页面
# run
# streamlit run app.py
"""

import dotenv
dotenv.load_dotenv(override=True)

import warnings
warnings.filterwarnings("ignore", message=".*__path__.*")

import streamlit as st
import time


from agent.react_agent import ReactAgent


# 标题
st.title("智扫通机器人智能客服")
st.divider()


if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

if "messages" not in st.session_state:
    st.session_state["messages"] = []   # {"role": "user", "content": "你好"}


for message in st.session_state["messages"]:
    st.chat_message(message["role"]).write(message["content"])
    # 如果消息附带 RAG 参考文档，渲染折叠展示
    if message.get("rag_docs"):
        with st.expander("查看参考资料", expanded=False):
            for entry in message["rag_docs"]:
                st.caption(f"检索词: {entry['query']}")
                for i, doc in enumerate(entry["docs"], 1):
                    st.markdown(f"**参考资料 {i}**")
                    st.info(doc[:500] + ("..." if len(doc) > 500 else ""))

# 用户输入提示词
prompt = st.chat_input()


if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["messages"].append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        text_placeholder = st.empty()

        full_text = ""
        rag_entries: list[dict] = []

        with st.spinner("思考中..."):
            for chunk in st.session_state["agent"].execute_stream(prompt):
                if isinstance(chunk, dict) and chunk.get("type") == "text":
                    full_text += chunk["content"]
                    text_placeholder.write(full_text + "▌")
                    time.sleep(0.01)
                elif isinstance(chunk, dict) and chunk.get("type") == "rag_docs":
                    rag_entries.append(chunk)
                else:
                    # 向后兼容：处理旧版纯字符串 chunk
                    full_text += str(chunk)
                    text_placeholder.write(full_text + "▌")
                    time.sleep(0.01)

        # 最终渲染（去掉光标）
        text_placeholder.write(full_text)

    # 将 RAG 文档一并存入 session，供 rerun 后历史循环渲染
    st.session_state["messages"].append({
        "role": "assistant",
        "content": full_text,
        "rag_docs": rag_entries if rag_entries else None,
    })
    st.rerun()

