from abc import ABC, abstractmethod
from typing import Optional
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings


from utils.config_handler import agent_conf


class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass


class ChatModelFactory(BaseModelFactory):
    def generator(self) -> BaseChatModel:
        return ChatTongyi(model=agent_conf["chat_model_name"]) # type: ignore
    

class EmbeddingsFactory(BaseModelFactory):
    def generator(self) -> Embeddings:
        return DashScopeEmbeddings(model=agent_conf["embedding_model_name"]) # type: ignore
    

chat_model = ChatModelFactory().generator()
embedding_model = EmbeddingsFactory().generator()


