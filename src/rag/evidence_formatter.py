"""
근거(Evidence) 포매터 모듈.

RAG 파이프라인에서 검색된 문서, 지식 그래프 트리플, 웹 검색 스니펫 등을
LLM이 답변 생성에 바로 사용할 수 있는 정돈된 한국어 컨텍스트 블록으로 변환한다.

주요 책임:
    - 그래프 검색 결과(보상/요구 조건)를 사람이 읽기 좋은 한 줄 요약으로 변환
    - Tavily 등 외부 검색 원문에서 잡음(raw 필드)을 제거
    - 길이 제한 및 출처(content_source) 표기를 통일
    - '진 힐라 vs 힐라'처럼 질문-근거 미스매치를 LLM에게 경고로 알림
"""

from __future__ import annotations

from common.state import AgentState, RetrievedDocument


# === 상수 정의 ===
# 한 답변에 포함시킬 최대 근거 개수 (프롬프트 비대화 및 LLM 혼란 방지)
MAX_EVIDENCE_COUNT = 6
# 단일 스니펫 최대 글자 수 (토큰 사용량 절약 및 가독성 확보)
MAX_SNIPPET_CHARS = 300

# 원본(raw) 컨텍스트에서 흔히 나타나는 마커 - 사용자에게 노출되면 안 되는 내부 메타데이터
RAW_CONTEXT_MARKERS = (
    "boss_properties:",
    "reward_properties:",
    "requirement_properties:",
    "retrieval_method:",
    "relevance_reason:",
    "source: graph::",
    "Graph boss",
)

# 답변 컨텍스트에서 제외해야 할 필드명 (출처/점수/내부 속성 등은 LLM 입력에서 제거)
RAW_FIELD_NAMES = {
    "source",
    "reliability",
    "retrieval_method",
    "score",
    "freshness",
    "relevance_reason",
    "boss_properties",
    "reward_properties",
    "requirement_properties",
}


# === 메인 엔트리포인트 ===
def format_evidence_for_answer(state: AgentState) -> AgentState:
    """AgentState의 근거 문서들을 정리해 답변용 context로 재작성한다.

    selected_evidence(선택된 근거)가 있으면 우선 사용하고,
    없으면 retrieved_docs(전체 검색 결과)를 폴백으로 사용한다.
    포매팅 결과는 tool_results에 메타 정보와 함께 기록되어 디버깅에 활용된다.
    """
    # 선택된 근거가 우선, 없으면 전체 검색 결과로 폴백 (빈 리스트도 안전하게 처리)
    documents = list(state.get("selected_evidence") or state.get("retrieved_docs") or [])
    original_context = str(state.get("context") or "")
    formatted_context = build_answer_context(
        # 재작성된 질의(contextualized_query)가 있으면 그것을, 없으면 원본 사용자 질문 사용
        question=str(state.get("contextualized_query") or state.get("user_query") or ""),
        documents=documents,
        original_context=original_context,
    )

    # 기존 tool_results를 보존하면서 포매터의 동작 결과를 추가 기록 (관찰성/디버깅 목적)
    tool_results = dict(state.get("tool_results", {}) or {})
    tool_results["evidence_formatter"] = {
        "document_count": len(documents),
        "raw_context_detected": contains_raw_context(original_context),
        "context_rewritten": formatted_context != original_context,
    }

    # state는 불변(immutable) 패턴으로 다루며, 변경된 필드만 덮어쓴 새 dict 반환
    return {
        **state,
        "context": formatted_context,
        "tool_results": tool_results,
    }


# === 컨텍스트 빌더 ===
def build_answer_context(
    *,
    question: str,
    documents: list[RetrievedDocument],
    original_context: str,
) -> str:
    """문서 리스트로부터 LLM이 사용할 최종 컨텍스트 문자열을 조립한다.

    근거가 없으면 원본 context를 정제해 반환하고,
    있으면 헤더 + (선택적 경고) + 문서별 요약 라인을 결합한다.
    """
    # 엣지 케이스: 근거 문서가 전혀 없으면 원본 컨텍스트만 정제해 반환
    if not documents:
        return clean_context_snippet(original_context)

    # 헤더 문구로 LLM에게 "여기부터 정리된 근거"임을 명시
    lines = ["사용자 답변에 사용할 정리된 근거입니다."]
    # 질문-근거 불일치 경고(예: 진 힐라 vs 힐라)가 있으면 상단에 삽입
    mismatch_notice = build_query_mismatch_notice(question, documents)
    if mismatch_notice:
        lines.extend(["", mismatch_notice])

    lines.append("")
    # MAX_EVIDENCE_COUNT 만큼만 잘라 프롬프트 길이 폭증 방지
    for document in documents[:MAX_EVIDENCE_COUNT]:
        lines.append(format_document_summary(document))

    # None 라인을 거르고 양 끝 공백 제거 후 줄바꿈으로 결합
    return "\n".join(line for line in lines if line is not None).strip()


# === 질문-근거 미스매치 경고 ===
def build_query_mismatch_notice(
    question: str,
    documents: list[RetrievedDocument],
) -> str:
    """질문은 '진 힐라'인데 근거가 '힐라'인 경우처럼 명확한 미스매치를 감지해 경고 문구를 만든다.

    메이플스토리에서 '힐라'와 '진 힐라'는 서로 다른 보스이므로,
    LLM이 잘못된 보상을 답변하지 않도록 사전에 주의를 환기한다.
    """
    # 공백 제거 + 소문자 정규화로 띄어쓰기/표기 변형 흡수
    normalized_question = str(question or "").replace(" ", "").lower()
    # 질문에 '진힐라'가 없다면 이 경고 로직 자체가 불필요
    if "진힐라" not in normalized_question:
        return ""

    # 근거 문서들의 page_content를 모두 합쳐 단일 텍스트로 검색
    evidence_text = " ".join(
        str(document.get("page_content") or "")
        for document in documents
    ).replace(" ", "").lower()
    # 근거 안에 한국어/영문 어느 표기로든 '진 힐라'가 등장하면 미스매치 아님
    if "진힐라" in evidence_text or "verushilla" in evidence_text:
        return ""

    # 질문은 진 힐라인데 근거는 일반 힐라뿐인 케이스 → LLM에게 단정 답변 금지 지시
    return (
        "주의: 선택된 근거는 '진 힐라'가 아니라 '힐라/Hilla' 관련 정보입니다. "
        "이 근거만으로는 진 힐라 보상이라고 단정할 수 없습니다."
    )


# === 문서 타입별 요약 라우터 ===
def format_document_summary(document: RetrievedDocument) -> str:
    """문서 한 건을 검색 방식(retrieval_method)에 따라 적절한 포맷터로 위임한다.

    그래프 기반 결과는 구조화된 필드를 활용해 보스/보상/요구사항 형식으로,
    일반 문서는 제목 + 출처 표기 + 정제된 스니펫 형식으로 변환한다.
    """
    metadata = document.get("metadata", {}) or {}
    retrieval_method = str(metadata.get("retrieval_method") or "")

    # 지식 그래프에서 가져온 보상/요구 조건 정보는 구조화 필드 기반으로 요약한다.
    if "graph_reward" in retrieval_method or "graph_requirement" in retrieval_method:
        fields = parse_context_fields(str(document.get("page_content") or ""))
        return format_graph_summary(fields, retrieval_method)

    # 일반 검색 결과: 제목이 없으면 source, 그것도 없으면 '근거'로 폴백
    title = str(metadata.get("title") or document.get("source") or "근거")
    snippet = clean_context_snippet(str(document.get("page_content") or ""))
    source_note = format_content_source_note(metadata)
    return f"- {title}{source_note}: {snippet}"


# === 출처 표기(citation) 헬퍼 ===
def format_content_source_note(metadata: dict) -> str:
    """본문이 어떤 경로로 수집되었는지 짧은 한국어 라벨로 변환한다.

    Tavily 스니펫만 있는지, 원문(raw)인지, 실제로 페이지를 크롤링했는지에 따라
    LLM이 신뢰도를 판단할 수 있도록 단서를 제공한다.
    """
    content_source = str(metadata.get("content_source") or "")
    fetch_status = str(metadata.get("fetch_status") or "")
    # Tavily 검색 스니펫만 있는 경우: fetch 실패 등의 상태를 함께 노출
    if content_source == "tavily_snippet_fallback":
        return f" (검색 스니펫 기반, fetch_status={fetch_status or 'unknown'})"
    # Tavily가 제공한 raw content를 그대로 사용한 경우
    if content_source == "tavily_raw_content":
        return " (Tavily raw content)"
    # 실제 페이지를 가져와 본문을 추출한 경우 (가장 신뢰도 높음)
    if content_source == "fetched_page":
        return " (실제 페이지 본문)"
    # 알 수 없는 출처는 표기 생략
    return ""


# === 그래프 근거 포매터 ===
def format_graph_summary(fields: dict[str, str], retrieval_method: str) -> str:
    """지식 그래프 보상/요구조건 근거를 한 줄 요약으로 변환한다.

    필드가 비어 있어도 자연스러운 한국어가 되도록 기본값을 채워준다.
    """
    boss = fields.get("Boss") or "대상 보스"
    difficulty = fields.get("difficulty")
    boss_label = f"{boss}({difficulty})" if difficulty else boss

    if "graph_reward" in retrieval_method:
        reward = fields.get("Reward") or "확인된 보상"
        details = [
            item
            for item in (
                fields.get("description"),
                fields.get("reward_type"),
                fields.get("value_type"),
            )
            if item
        ]
        detail_text = f" - {', '.join(details)}" if details else ""
        return f"- {boss_label}: {reward}{detail_text}"

    stat_parts = []
    for label, key in (
        ("요구 레벨", "required_level"),
        ("주스탯", "main_stat"),
        ("아케인포스", "arcane_force"),
        ("어센틱포스", "authentic_force"),
        ("보공", "boss_damage"),
        ("방무", "ignore_def"),
    ):
        value = fields.get(key)
        if value:
            stat_parts.append(f"{label} {value}")

    detail = ", ".join(stat_parts) if stat_parts else "요구 조건 근거가 확인되었습니다"
    return f"- {boss_label}: {detail}"


# === 파서/정제 유틸 ===
def parse_context_fields(content: str) -> dict[str, str]:
    """'key: value' 형태의 본문을 dict로 파싱하되, 내부 메타 필드는 제외한다.

    그래프 검색 결과는 줄바꿈으로 구분된 key:value 리스트 형태로 들어오므로
    이를 dict로 만들어 그래프 포매터들이 쉽게 꺼내 쓸 수 있게 한다.
    """
    fields: dict[str, str] = {}
    for line in content.splitlines():
        # 'key: value' 패턴이 아닌 라인은 스킵 (구분자가 없으면 의미 있는 필드가 아님)
        if ": " not in line:
            continue

        # 첫 번째 ': '만 분리해 값에 콜론이 포함되어도 안전하게 처리
        key, value = line.split(": ", 1)
        key = key.strip()
        # RAW 필드(출처/점수 등) 또는 *_properties류 잡음 필드는 무시
        if key in RAW_FIELD_NAMES or key.endswith("_properties"):
            continue

        value = value.strip()
        # 빈 값은 저장하지 않음 - 다운스트림에서 기본값 폴백을 받게 됨
        if value:
            fields[key] = value

    return fields


def clean_context_snippet(content: str) -> str:
    """원본 컨텍스트에서 잡음(raw 마커/메타 필드)을 제거하고 길이 제한을 적용한다.

    LLM에게는 사람이 읽을 수 있는 자연어만 보여줘야 하므로,
    내부 디버깅용 라인은 모두 걸러낸다.
    """
    clean_lines = []
    for line in str(content or "").splitlines():
        stripped = line.strip()
        # 빈 줄 또는 raw 마커가 포함된 줄은 제거
        if not stripped or contains_raw_context(stripped):
            continue
        # 'raw 필드명: ...' 형태의 메타 라인도 제거 (LLM 입력에서 노이즈 차단)
        if ": " in stripped and stripped.split(": ", 1)[0] in RAW_FIELD_NAMES:
            continue
        clean_lines.append(stripped)

    # 여러 줄을 단일 공백으로 합쳐 한 줄짜리 스니펫으로 만들기
    snippet = " ".join(clean_lines).strip()
    # 길이 제한 초과 시 말줄임표를 붙여 잘라낸다 (토큰 사용량 통제)
    if len(snippet) > MAX_SNIPPET_CHARS:
        return snippet[:MAX_SNIPPET_CHARS].rstrip() + "..."
    # 정제 결과가 비어 있는 엣지 케이스: 빈 문자열 대신 안내 문구 반환
    return snippet or "근거 내용을 요약할 수 없습니다."


def contains_raw_context(text: str) -> bool:
    """텍스트 안에 내부 raw 마커가 하나라도 포함되어 있는지 빠르게 검사한다."""
    # any() 단락 평가로 첫 매치에서 즉시 True 반환
    return any(marker in str(text or "") for marker in RAW_CONTEXT_MARKERS)
