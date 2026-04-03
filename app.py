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

# 用户输入提示词
prompt = st.chat_input()


if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.spinner("思考中..."):
        response_messages = []
        res_stream = st.session_state["agent"].execute_stream(prompt)
        def capture(generator, str_list):
            for chunk in generator:
                str_list.append(chunk)
                for char in chunk:
                    time.sleep(0.01)
                    yield char
        st.chat_message("assistant").write_stream(capture(res_stream, response_messages))
        st.session_state["messages"].append({"role": "assistant", "content": response_messages[-1]})
        st.rerun()

# run
# streamlit run app.py