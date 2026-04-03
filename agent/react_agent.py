from langchain.agents import create_agent


from model.factory import chat_model
from utils.prompt_loader import load_system_prompt
from agent.tools.agent_tools import (
    rag_summarize,
    get_weather,
    get_user_city,
    get_user_id,
    get_current_month,
    fetch_external_data,
    fill_context_for_report
)
from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompt(),
            tools=[
                rag_summarize,
                get_weather,
                get_user_city,
                get_user_id,
                get_current_month,
                fetch_external_data,
                fill_context_for_report
            ],
            middleware=[
                monitor_tool,
                log_before_model,
                report_prompt_switch
            ]
        )

    def execute_stream(self, query: str):
        input_dict = {
            "messages": [
                {"role": "user", "content": query}
            ]
        }

        response = self.agent.stream(input_dict, stream_mode="values", context={"report": False})
        for chunk in response:
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"



# python -m agent.react_agent
if __name__ == "__main__":
    query = "生成我这个月的使用报告。"
    agent = ReactAgent()
    for chunk in agent.execute_stream(query):
        print(chunk, end="")
