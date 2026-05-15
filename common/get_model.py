from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402


def get_embedding_model() -> OpenAIEmbeddings:
    emb = OpenAIEmbeddings(
        model="text-embedding-3-small"
    )
    return emb


def get_llm() -> ChatOpenAI:
    llm = ChatOpenAI(
        model="openai/gpt-5.4-nano",
        temperature=0.2,
    )
    return llm
