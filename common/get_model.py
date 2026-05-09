import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_groq import ChatGroq
    from langchain_openai import ChatOpenAI
    from langchain_openai import OpenAIEmbeddings

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_OPENAI_MODEL = "gpt-5.4-nano"
DEFAULT_LLM_TEMPERATURE = 0.2

LLM_PROVIDER_ENV = "LLM_PROVIDER"
GROQ_PROVIDER = "groq"
OPENAI_PROVIDER = "openai"


def get_embedding_model() -> "OpenAIEmbeddings":
    from langchain_openai import OpenAIEmbeddings

    emb = OpenAIEmbeddings(
        model=os.environ.get("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    )
    return emb


def get_llm() -> "ChatGroq | ChatOpenAI":
    provider = get_llm_provider()
    temperature = get_llm_temperature()

    if provider == GROQ_PROVIDER:
        return get_groq_llm(temperature)

    if provider == OPENAI_PROVIDER:
        return get_openai_llm(temperature)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def get_llm_provider() -> str:
    return (os.environ.get(LLM_PROVIDER_ENV) or DEFAULT_LLM_PROVIDER).strip().lower()


def has_llm_config() -> bool:
    provider = get_llm_provider()
    if provider == GROQ_PROVIDER:
        return bool(os.environ.get("GROQ_API_KEY"))
    if provider == OPENAI_PROVIDER:
        return bool(os.environ.get("OPENAI_API_KEY"))
    return False


def get_llm_temperature() -> float:
    return float(os.environ.get("LLM_TEMPERATURE", DEFAULT_LLM_TEMPERATURE))


def get_groq_llm(temperature: float) -> "ChatGroq":
    from langchain_groq import ChatGroq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is required.")

    return ChatGroq(
        api_key=api_key,
        model=os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL),
        temperature=temperature,
    )


def get_openai_llm(temperature: float) -> "ChatOpenAI":
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required.")

    return ChatOpenAI(
        api_key=api_key,
        model=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        temperature=temperature,
    )
