import os

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


from utils.config_handler import chroma_conf
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger
from model.factory import embedding_model


class VectorStoreService():
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=embedding_model,
            persist_directory=chroma_conf["persist_directory"],
        )
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(
            search_kwargs={"k": chroma_conf["k"]}
        )

    def load_documents(self) -> list[Document] | None:
        """
        读取chroma_conf["data_path"]文件夹内所有允许类型的文件，转为向量存入向量数据库
        """
        def check_md5_hex(md5_for_check: str):
            """检查md5是否存在文件中"""
            if not os.path.exists(get_abs_path(chroma_conf["md5_hex_store"])):
                open(get_abs_path(chroma_conf["md5_hex_store"]), "w", encoding="utf-8").close()
                return False
            with open(get_abs_path(chroma_conf["md5_hex_store"]), "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() == md5_for_check:
                        return True
                return False
            
        def save_md5_hex(md5_for_save: str):
            """保存md5到文件"""
            with open(get_abs_path(chroma_conf["md5_hex_store"]), "a", encoding="utf-8") as f:
                f.write(md5_for_save + "\n")

        def get_file_documents(file_path: str):
            """获取文件内容"""
            if file_path.endswith(".txt"):
                return txt_loader(file_path)
            elif file_path.endswith(".pdf"):
                return pdf_loader(file_path)
            return []

        allowed_file_paths = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allowed_knowledge_file_type"])
        )
        if not allowed_file_paths:
            return []
        
        for path in allowed_file_paths:
            md5_hex = get_file_md5_hex(path)
            if not md5_hex:
                continue
            if check_md5_hex(md5_hex):
                logger.info(f"[load_documents]文件内容已存在知识库: {path}")
                continue

            try:
                documents = get_file_documents(path)
                if not documents:
                    logger.warning(f"[load_documents]文件内容为空或异常: {path}")
                    continue
                split_documents: list[Document] = self.spliter.split_documents(documents)
                if not split_documents:
                    logger.warning(f"[load_documents]分片后为空或异常: {path}")
                    continue
                self.vector_store.add_documents(split_documents)
                save_md5_hex(md5_hex)
                logger.info(f"[load_documents]文件内容已添加到知识库: {path}")
            except Exception as e:
                logger.error(f"[load_documents]文件内容处理异常: {path}，异常信息: {str(e)}", exc_info=True)


if __name__ == "__main__":
    vector_store_service = VectorStoreService()
    vector_store_service.load_documents()
    retriever = vector_store_service.get_retriever()

    res = retriever.invoke("开不了机。")
    
    for item in res:
        print(item.page_content)
        print("="*50)
