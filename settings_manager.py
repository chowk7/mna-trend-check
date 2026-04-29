"""
GCS 기반 앱 설정 관리.
설정 파일(mna-settings.json)을 GCS 버킷에 읽고 씁니다.
GCS_SETTINGS_BUCKET 환경변수가 없으면 읽기는 {} 반환, 쓰기는 EnvironmentError를 발생시킵니다.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "mna-settings.json"


def _bucket_name() -> str:
    return os.environ.get("GCS_SETTINGS_BUCKET", "")


def _get_blob():
    from google.cloud import storage
    name = _bucket_name()
    client = storage.Client()
    return client.bucket(name).blob(_SETTINGS_FILE)


def load_settings() -> dict:
    """GCS에서 설정을 읽습니다. 버킷 미설정·파일 없음·오류 모두 {}를 반환합니다."""
    if not _bucket_name():
        logger.debug("GCS_SETTINGS_BUCKET 미설정 — 설정 로드 생략")
        return {}
    try:
        blob = _get_blob()
        if not blob.exists():
            return {}
        return json.loads(blob.download_as_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("GCS 설정 로드 실패: %s", e)
        return {}


def save_settings(settings: dict) -> None:
    """설정을 GCS에 씁니다. GCS_SETTINGS_BUCKET 미설정 시 EnvironmentError 발생."""
    if not _bucket_name():
        raise EnvironmentError(
            "GCS_SETTINGS_BUCKET 환경변수가 설정되지 않았습니다. "
            "Cloud Run 또는 로컬 환경에서 설정해 주세요."
        )
    blob = _get_blob()
    blob.upload_from_string(
        json.dumps(settings, ensure_ascii=False, indent=2),
        content_type="application/json",
    )
    logger.info("GCS 설정 저장 완료: gs://%s/%s", _bucket_name(), _SETTINGS_FILE)


def is_gcs_configured() -> bool:
    return bool(_bucket_name())
