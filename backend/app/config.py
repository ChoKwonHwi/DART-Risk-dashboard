"""환경변수 기반 설정. .env 파일을 로드하여 API 키와 경로를 노출한다."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

DART_API_KEY = os.getenv("DART_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CORP_CODE_XML_PATH = DATA_DIR / "CORPCODE.xml"
CACHE_DB_PATH = DATA_DIR / "cache.db"


def require_dart_key() -> str:
    if not DART_API_KEY:
        raise RuntimeError(
            "DART_API_KEY가 설정되지 않았습니다. .env 파일에 값을 채워주세요 "
            "(https://opendart.fss.or.kr 에서 발급)."
        )
    return DART_API_KEY


def require_openrouter_key() -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY가 설정되지 않았습니다. .env 파일에 값을 채워주세요 "
            "(https://openrouter.ai/keys 에서 발급)."
        )
    return OPENROUTER_API_KEY


def require_naver_credentials() -> tuple[str, str]:
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise RuntimeError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되지 않았습니다. .env 파일에 값을 채워주세요 "
            "(https://developers.naver.com/apps 에서 애플리케이션 등록 후 발급, '검색' API 사용 설정 필요)."
        )
    return NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
