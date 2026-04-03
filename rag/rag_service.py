"""
RAG服务模块
"""
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompt
from model.factory import chat_model, embedding_model


def print_prompt(prompt):
    print("="*20)
    print(prompt.to_string())
    print("="*20)
    return prompt


class RAGSummarizeService:
    def __init__(self):
        self.vector_store_service = VectorStoreService()
        self.retriever = self.vector_store_service.get_retriever()
        self.prompt_text = load_rag_prompt()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = chat_model
        self.chain = self._init_chain()

    def _init_chain(self):
        return self.prompt_template | self.model | StrOutputParser()
    
    def retriever_docs(self, query: str) -> list[Document]:
        return self.retriever.invoke(query)
    
    def rag_summarize(self, query: str) -> str:
        context_docs = self.retriever_docs(query)
        context = ""
        counter = 0
        for doc in context_docs:
            counter += 1
            context += f"【参考资料{counter}】：{doc.page_content} | 参考元数据：{doc.metadata}\n\n"
        return self.chain.invoke({"input": query, "context": context})
    


if __name__ == "__main__":
    query = "小户型适合哪些扫地机器人？"
    rag_service = RAGSummarizeService()
    print(rag_service.rag_summarize(query))