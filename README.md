# M&A 뉴스 요약기

특정 날짜 범위의 M&A 뉴스를 검색하고, Gemini AI로 요약해주는 Streamlit 웹 앱입니다.

## 기능

- **날짜 범위 설정**: 원하는 기간의 M&A 뉴스 검색
- **뉴스 검색**: Google 뉴스에서 인수합병, merger, acquisition, JV, divest 등 키워드로 자동 검색
- **기사 선택**: 목록에서 요약할 기사 선택 (전체 선택/해제 지원)
- **AI 요약**: Gemini 1.5 Flash/Pro로 선택 기사 요약
- **양식 커스터마이징**: 요약 양식 및 규칙을 자유롭게 수정 가능
- **결과 다운로드**: 전체 요약을 txt 파일로 다운로드

## 아키텍처

- **UI**: Streamlit
- **뉴스 소스**: Google News RSS (무료, API 키 불필요)
- **AI 요약**: Google Gemini API
- **시크릿 관리**: GCP Secret Manager
- **배포**: GCP Cloud Run

## GCP 설정

### 1. Secret Manager에 Gemini API 키 저장

```bash
gcloud secrets create gemini-api-key --replication-policy="automatic"
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
```

### 2. Cloud Run 서비스 계정 권한 설정

```bash
# 서비스 계정에 Secret Manager 접근 권한 부여
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 3. Cloud Run 배포

```bash
gcloud run deploy mna-news-app \
  --source . \
  --region asia-northeast3 \
  --set-env-vars GCP_PROJECT_ID=YOUR_PROJECT_ID \
  --allow-unauthenticated
```

## 로컬 개발

GCP 인증 후 실행:

```bash
gcloud auth application-default login

pip install -r requirements.txt
GCP_PROJECT_ID=YOUR_PROJECT_ID streamlit run app.py
```

## Cloud Run 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `GCP_PROJECT_ID` | GCP 프로젝트 ID | (필수) |
| `GEMINI_SECRET_ID` | Secret Manager 시크릿 이름 | `gemini-api-key` |
