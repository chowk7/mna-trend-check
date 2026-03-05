import os

from google.api_core.exceptions import NotFound, PermissionDenied
from google.cloud import secretmanager


def get_gemini_api_key(
    project_id: str | None = None,
    secret_id: str | None = None,
    version: str = "latest",
) -> str:
    """GCP Secret Manager에서 Gemini API 키를 가져옵니다."""
    project_id = project_id or os.environ.get("GCP_PROJECT_ID")
    secret_id = secret_id or os.environ.get("GEMINI_SECRET_ID", "gemini-api-key")

    if not project_id:
        raise EnvironmentError(
            "GCP_PROJECT_ID 환경변수가 설정되지 않았습니다. "
            "Cloud Run 환경변수 또는 로컬 환경에서 설정해 주세요."
        )

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"

    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except NotFound:
        raise RuntimeError(
            f"Secret '{secret_id}'을(를) 프로젝트 '{project_id}'에서 찾을 수 없습니다. "
            "Secret Manager에 시크릿이 생성되어 있는지 확인해 주세요."
        )
    except PermissionDenied:
        raise RuntimeError(
            f"Secret '{secret_id}'에 접근 권한이 없습니다. "
            "Cloud Run 서비스 계정에 'Secret Manager Secret Accessor' 역할이 부여되어 있는지 확인해 주세요."
        )
