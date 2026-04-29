"""
GCS 기반 설정 저장소 - Google CSE / Naver News 설정 관리
server.py에서 사용하는 플랫 키 구조 사용
"""
import json
import logging
import os
from typing import Any

from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

# GCS 설정 파일 이름
SETTINGS_FILE = "settings.json"

# 기본값 (플랫 키 구조 - server.py와 호환)
DEFAULT_SETTINGS = {
    "cse_api_key": "AIzaSyDLPbiIhfTeIaFP2JPaC3vEBpowOwKYhVA",
    "cse_cx": "620f073b5bf414784",
    "naver_client_id": "_jOicpv_8TEwG0M3VpLK",
    "naver_client_secret": "KmUiTp1kgi",
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
    """GCS에 설정 저장
    
    Args:
        settings: 플랫 키 딕셔너리 {
            "cse_api_key": str,
            "cse_cx": str,
            "naver_client_id": str,
            "naver_client_secret": str
        }
    """
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
    return {
        "api_key": settings.get("cse_api_key", ""),
        "search_engine_id": settings.get("cse_cx", ""),
    }


def get_naver_settings() -> dict:
    """Naver News 설정 반환"""
    settings = load_settings()
    return {
        "client_id": settings.get("naver_client_id", ""),
        "client_secret": settings.get("naver_client_secret", ""),
    }


def update_cse_settings(api_key: str = None, search_engine_id: str = None, enabled: bool = None) -> bool:
    """Google CSE 설정 업데이트"""
    settings = load_settings()

    if api_key is not None:
        settings["cse_api_key"] = api_key
    if search_engine_id is not None:
        settings["cse_cx"] = search_engine_id
    # enabled는 UI에서 관리하므로 여기서는 저장하지 않음

    return save_settings(settings)


def update_naver_settings(client_id: str = None, client_secret: str = None, enabled: bool = None) -> bool:
    """Naver News 설정 업데이트"""
    settings = load_settings()

    if client_id is not None:
        settings["naver_client_id"] = client_id
    if client_secret is not None:
        settings["naver_client_secret"] = client_secret
    # enabled는 UI에서 관리하므로 여기서는 저장하지 않음

    return save_settings(settings)


def is_gcs_configured() -> bool:
    """GCS가 설정되었는지 확인"""
    try:
        client = _get_gcs_client()
        bucket = client.bucket(_get_bucket_name())
        return bucket.exists()
    except Exception:
        return False
