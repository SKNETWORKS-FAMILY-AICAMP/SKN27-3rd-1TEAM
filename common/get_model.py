from dotenv import load_dotenv

load_dotenv()


from langchain_openai import ChatOpenAI  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402


def get_embedding_model() -> OpenAIEmbeddings:
    emb = OpenAIEmbeddings(
        model="text-embedding-3-small"
    )
    return emb


def get_llm() -> ChatGroq:
    llm = ChatGroq(
        model="openai/gpt-oss-120b"
    )
    return llm
