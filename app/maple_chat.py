from __future__ import annotations

import streamlit as st

from src.services.chat_service import run_research_chat


def main() -> None:
    st.set_page_config(page_title="MapleStory Research Chat", page_icon="M")
    st.title("MapleStory Research Chat")

    message = st.text_input("Question", placeholder="Example: Normal Lotus requirement")
    character_name = st.text_input("Character name", placeholder="Optional")
    world_name = st.text_input("World name", placeholder="Optional")

    if st.button("Search") and message.strip():
        with st.spinner("Research Agent is collecting evidence."):
            response = run_research_chat(
                message.strip(),
                character_name=character_name.strip() or None,
                world_name=world_name.strip() or None,
            )

        st.subheader("Answer")
        st.write(response["answer"])

        if response.get("sources"):
            st.subheader("Sources")
            st.dataframe(response["sources"], use_container_width=True)

        if response.get("errors"):
            st.subheader("Execution Errors")
            st.write(response["errors"])

        with st.expander("Research Context"):
            st.text(response.get("context", ""))


if __name__ == "__main__":
    main()
