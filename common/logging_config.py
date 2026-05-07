import logging
import os
from logging.handlers import TimedRotatingFileHandler


def set_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)

    #로그 생성
    logger = logging.getLogger("post_mk_pipe_logger") #로그 이름 설정
    logger.setLevel(logging.INFO) #로그 레벨 설정
    logger.propagate = False #로그 전파 방지

    if logger.handlers: #이미 핸들러가 있으면 기존 핸들러 반환
        return logger

    #파일 핸들러 설정(로그 출력)
    handler = TimedRotatingFileHandler(
        filename="logs/postmake.log", #파일 이름
        when="midnight", # 매일 자정 갱신
        interval=1, #하루단위 생성
        backupCount=24, #24개 파일 저장
        encoding="utf-8" #인코딩 설정
    )
    # 파일에는 실패 관련 로그만 남김
    handler.setLevel(logging.WARNING)
    handler.suffix = "%Y-%m-%d" #파일 이름 형식

    #로그 형식 설정
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler) #로그 핸들러 추가

    # 콘솔 핸들러를 추가해 실행 상태를 터미널에서도 확인 가능하게 함
    console_handler = logging.StreamHandler()
    # 터미널에는 단계/성공 로그 포함 전체 진행 상황 출력
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)
    return logger

