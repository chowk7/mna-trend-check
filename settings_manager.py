"""
GCS 기반 설정 저장소 - Google CSE / Naver News 설정 관리
"""
import json
import logging
import os
from datetime import date
from typing import Any

from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

# GCS 설정 파일 이름
SETTINGS_FILE = "settings.json"

# 기본값
DEFAULT_SETTINGS = {
    "google_cse": {
        "enabled": False,
        "api_key": "",
        "search_engine_id": "",
    },
    "naver_news": {
        "enabled": False,
        "client_id": "",
        "client_secret": "",
    },
}


def _get_gcs_client():
    """GCS 클라이언트 생성 (ADC 또는 service account 사용)"""
    try:
        # ADC (Application Default Credentials) 사용 시도
        client = storage.Client()
        return client
    except Exception:
        pass

    # 환경변수의 service account JSON 사용
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        try:
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            client = storage.Client(credentials=credentials)
            return client
        except Exception as e:
            logger.warning(f"Service account 파일 로드 실패: {e}")
            raise

    raise EnvironmentError(
        "GCS 접근 불가: GOOGLE_APPLICATION_CREDENTIALS 환경변수 설정 또는 ADC 필요"
    )


def _get_bucket_name() -> str:
    """버킷 이름 반환"""
    return os.environ.get("GCS_BUCKET_NAME", "concise-mesh-399505.appspot.com")


def load_settings() -> dict:
    """GCS에서 설정 로드 (로컬 캐시 우선)"""
    # memory 캐시 확인
    if hasattr(load_settings, "_cache"):
        return load_settings._cache

    try:
        client = _get_gcs_client()
        bucket = client.bucket(_get_bucket_name())
        blob = bucket.blob(SETTINGS_FILE)

        if blob.exists():
            content = blob.download_as_text()
            settings = json.loads(content)
            logger.info("GCS에서 설정 로드 완료")
        else:
            settings = DEFAULT_SETTINGS.copy()
            logger.info("설정 파일 없음, 기본값 사용")

        load_settings._cache = settings
        return settings

    except Exception as e:
        logger.warning(f"GCS 로드 실패, 기본값 사용: {e}")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> bool:
    """GCS에 설정 저장"""
    try:
        client = _get_gcs_client()
        bucket = client.bucket(_get_bucket_name())
        blob = bucket.blob(SETTINGS_FILE)

        blob.upload_from_text(json.dumps(settings, ensure_ascii=False, indent=2))
        logger.info("GCS에 설정 저장 완료")

        # 메모리 캐시 갱신
        if hasattr(load_settings, "_cache"):
            load_settings._cache.clear()
        load_settings._cache = settings

        return True

    except Exception as e:
        logger.error(f"GCS 저장 실패: {e}")
        return False


def get_cse_settings() -> dict:
    """Google CSE 설정 반환"""
    settings = load_settings()
    return settings.get("google_cse", DEFAULT_SETTINGS["google_cse"])


def get_naver_settings() -> dict:
    """Naver News 설정 반환"""
    settings = load_settings()
    return settings.get("naver_news", DEFAULT_SETTINGS["naver_news"])


def update_cse_settings(api_key: str = None, search_engine_id: str = None, enabled: bool = None) -> bool:
    """Google CSE 설정 업데이트"""
    settings = load_settings()
    cse = settings.get("google_cse", {})

    if api_key is not None:
        cse["api_key"] = api_key
    if search_engine_id is not None:
        cse["search_engine_id"] = search_engine_id
    if enabled is not None:
        cse["enabled"] = enabled

    settings["google_cse"] = cse
    return save_settings(settings)


def update_naver_settings(client_id: str = None, client_secret: str = None, enabled: bool = None) -> bool:
    """Naver News 설정 업데이트"""
    settings = load_settings()
    naver = settings.get("naver_news", {})

    if client_id is not None:
        naver["client_id"] = client_id
    if client_secret is not None:
        naver["client_secret"] = client_secret
    if enabled is not None:
        naver["enabled"] = enabled

    settings["naver_news"] = naver
    return save_settings(settings)
