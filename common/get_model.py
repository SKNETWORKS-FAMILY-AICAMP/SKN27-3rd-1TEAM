from langchain_openai import OpenAIEmbeddings
from langchain_groq import ChatGroq


def get_embedding_model() -> OpenAIEmbeddings:
    emb = OpenAIEmbeddings(
        model="text-embedding-3-small"
    )
    return emb


def get_llm() -> ChatGroq:
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.2,
    )
    return llm
