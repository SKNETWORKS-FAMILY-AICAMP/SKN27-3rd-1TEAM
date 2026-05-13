from langchain_openai import OpenAIEmbeddings, ChatOpenAI
#from langchain_groq import ChatGroq
from dotenv import load_dotenv
load_dotenv()


def get_embedding_model() -> OpenAIEmbeddings:
    emb = OpenAIEmbeddings(
        model="text-embedding-3-small"
    )
    return emb


def get_llm() -> ChatOpenAI:
    llm = ChatOpenAI(
        model="gpt-5.4-mini",
        temperature=0.2,
    )
    return llm
