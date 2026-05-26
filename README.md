# 사내 통합검색 + 웹하드 (FastAPI + Milvus + MinIO)

이 저장소는 다음 2개 시스템을 한 번에 운영하기 위한 MVP 템플릿입니다.

- 통합검색 서버: 문서를 벡터로 인덱싱하고 의미 기반 검색
- 웹하드 서버: 파일 업로드/목록/다운로드 URL/삭제

## 1) 아키텍처

- API
	- `search-api` (FastAPI): 인덱싱(`/index`), 검색(`/search`)
	- `webhard-api` (FastAPI): 파일 업로드/목록/삭제/다운로드 URL
- 데이터 계층
	- `Milvus`: 벡터 저장/검색
	- `MinIO`: 파일 저장소(웹하드), Milvus 내부 오브젝트 스토리지
	- `etcd`: Milvus 메타데이터 저장

## 2) 디렉터리 구조

```text
.
├── docker-compose.yml
├── .env.example
└── services
		├── search_api
		│   ├── Dockerfile
		│   ├── requirements.txt
		│   └── app
		│       ├── main.py
		│       ├── milvus_store.py
		│       ├── schemas.py
		│       ├── security.py
		│       ├── settings.py
		│       └── vectorizer.py
		└── webhard_api
				├── Dockerfile
				├── requirements.txt
				└── app
						├── main.py
						├── security.py
						├── settings.py
						└── storage.py
```

## 3) 빠른 시작

1. 환경변수 파일 생성

```bash
cp .env.example .env
```

Webhard DB 옵션:

- 기본값: `WEBHARD_DB_PATH` 기반 sqlite 사용
- `DATABASE_URL` 설정 시 해당 DB 사용
	- `sqlite:////data/webhard.db`
	- `mysql+pymysql://user:pass@host:3306/webhard`
	- `postgresql+psycopg://user:pass@host:5432/webhard`
	- `oracle+oracledb://user:pass@host:1521/?service_name=SERVICE`

라우터 SQL 관리:

- 라우터에서 사용하는 SQL은 `services/webhard_api/app/sql/*_queries.py` 형태로 라우터 파일 기준 분리 관리

임베딩 옵션:

- `EMBEDDING_ENABLED=true` : `/index`, `/search` 사용 가능
- `EMBEDDING_ENABLED=false` : 임베딩 비활성화(해당 API 호출 시 400 응답)
- `EMBEDDING_PROVIDER=hash|openai|sentence_transformers|bge_m3`
- `EMBEDDING_MODEL`
	- `openai` 사용 시: 예) `text-embedding-3-small`
	- `sentence_transformers` 사용 시: 예) `BAAI/bge-m3`
- `EMBEDDING_BGE_MODEL`: `bge_m3` provider 모델명 (기본값: `BAAI/bge-m3`)
- `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY` : `openai` provider에서 사용
- `EMBEDDING_MAX_LENGTH`, `EMBEDDING_DEVICE` : `bge_m3` provider에서 사용
- 성능 옵션:
	- `EMBEDDING_BATCH_SIZE` : 인덱싱 시 배치 임베딩 크기 (특히 `bge_m3`에서 효과 큼)
	- `EMBEDDING_AUTO_BATCH` : 텍스트 길이 기반 배치 자동 튜닝 on/off
	- `EMBEDDING_MAX_CONCURRENCY` : 임베딩 동시 처리 제한(요청 큐 역할)
- 차원 자동 검증:
	- 임베딩 벡터 길이와 `VECTOR_DIM`이 다르면 `/index`, `/search`는 400 에러 반환
	- 기존 Milvus 컬렉션의 `embedding dim`과 `VECTOR_DIM`이 다르면 기본값은 서버 시작 시 오류로 중단
	- `MILVUS_AUTO_MIGRATE_DIM=true` 이면 기존 컬렉션을 백업 이름으로 변경 후 새 차원으로 재생성
- Milvus 마이그레이션 옵션:
	- `MILVUS_AUTO_MIGRATE_DIM=false|true`
	- `MILVUS_BACKUP_PREFIX=backup` (백업 컬렉션 이름 접두사)

2. 컨테이너 실행

```bash
docker compose up -d --build
```

3. 헬스체크

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

4. MinIO 콘솔 접속

- URL: `http://localhost:9001`
- 계정: `.env`의 `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`

## 4) 통합검색 API 사용 예시

공통 헤더:

```bash
export API_KEY=change-me
```

문서 인덱싱:

```bash
curl -X POST "http://localhost:8000/index" \
	-H "Content-Type: application/json" \
	-H "x-api-key: ${API_KEY}" \
	-d '{
		"document_id": "hr-policy-001",
		"title": "인사 규정",
		"text": "연차 사용 규정과 승인 프로세스를 설명합니다...",
		"source_path": "docs/hr/policy.md",
		"metadata": {"dept": "HR", "security": "internal"}
	}'
```

검색:

```bash
curl -X POST "http://localhost:8000/search" \
	-H "Content-Type: application/json" \
	-H "x-api-key: ${API_KEY}" \
	-d '{
		"query": "연차 승인 절차",
		"top_k": 5
	}'
```

provider 예시:

```bash
# 1) 기본(데모) 해시 임베딩
EMBEDDING_PROVIDER=hash

# Milvus dim 불일치 시 자동 마이그레이션 사용
MILVUS_AUTO_MIGRATE_DIM=true
MILVUS_BACKUP_PREFIX=backup

# 2) OpenAI 호환 임베딩 API
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_API_KEY=your_api_key

# 3) sentence-transformers 로컬 모델
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-m3

# 4) bge-m3 순수 파이썬(Transformers + PyTorch, SentenceTransformer 미사용)
EMBEDDING_PROVIDER=bge_m3
EMBEDDING_BGE_MODEL=BAAI/bge-m3
EMBEDDING_MAX_LENGTH=512
EMBEDDING_BATCH_SIZE=16
EMBEDDING_AUTO_BATCH=true
EMBEDDING_MAX_CONCURRENCY=2
EMBEDDING_DEVICE=cpu
# bge-m3 dense 벡터는 보통 1024 차원
VECTOR_DIM=1024
```

임베딩 메트릭 확인:

```bash
curl -X GET "http://localhost:8000/metrics/embedding" \
	-H "x-api-key: ${API_KEY}"
```

간단 부하 테스트:

```bash
chmod +x ./scripts/load_test_search.sh
API_KEY=change-me CONCURRENCY=8 REQUESTS=80 ./scripts/load_test_search.sh
```

## 5) 웹하드 API 사용 예시

신규 Nextcloud 스타일 핵심 기능:

- 계정 등록/로그인(Bearer Token)
- 폴더 생성
- 파일 업로드 + 버전 관리
- 공유 링크(만료/비밀번호/1회성/최대 다운로드 횟수)
- 파일 ACL (user/group/public 권한)
- 그룹/그룹 멤버 관리
- 휴지통 이동/복원

계정 등록:

```bash
curl -X POST "http://localhost:8001/nc/auth/register" \
	-H "Content-Type: application/json" \
	-d '{"username":"alice","password":"alice-pass-123"}'
```

로그인:

```bash
TOKEN=$(curl -sS -X POST "http://localhost:8001/nc/auth/login" \
	-H "Content-Type: application/json" \
	-d '{"username":"alice","password":"alice-pass-123"}' | jq -r '.access_token')
```

폴더 생성:

```bash
curl -X POST "http://localhost:8001/nc/folders" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"path":"team/docs"}'
```

파일 업로드(논리 경로 지정):

```bash
curl -X POST "http://localhost:8001/nc/files/upload?path=team/docs/README.md" \
	-H "Authorization: Bearer ${TOKEN}" \
	-F "file=@./README.md"
```

파일 목록:

```bash
curl -X GET "http://localhost:8001/nc/files?prefix=team/docs" \
	-H "Authorization: Bearer ${TOKEN}"
```

버전 목록:

```bash
curl -X GET "http://localhost:8001/nc/files/1/versions" \
	-H "Authorization: Bearer ${TOKEN}"
```

공유 링크 생성:

```bash
curl -X POST "http://localhost:8001/nc/files/1/share" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"expires_in_sec":3600,"password":"1234"}'
```

공유 링크 생성(1회성, 최대 다운로드 횟수):

```bash
curl -X POST "http://localhost:8001/nc/files/1/share" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"expires_in_sec":3600,"one_time":true,"max_downloads":1}'
```

공유 링크 생성(다운로드 비활성 + 업로드 허용):

```bash
curl -X POST "http://localhost:8001/nc/files/1/share" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"expires_in_sec":3600,"allow_download":false,"allow_upload":true}'
```

공유 링크로 업로드(버전 추가):

```bash
curl -X POST "http://localhost:8001/nc/shares/<share_token>/upload-version" \
	-F "file=@./README.md"
```

그룹 생성 및 멤버 추가:

```bash
curl -X POST "http://localhost:8001/nc/groups" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"name":"teamA"}'

curl -X POST "http://localhost:8001/nc/groups/1/members/2" \
	-H "Authorization: Bearer ${TOKEN}"
```

파일 권한 부여(그룹 읽기/업로드 권한):

```bash
curl -X POST "http://localhost:8001/nc/files/1/permissions" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"subject_type":"group","subject_id":1,"can_read":true,"can_upload":true,"can_manage":false}'
```

폴더 권한 부여(하위 신규 파일 자동 상속 + 기존 파일 일괄 반영):

```bash
curl -X POST "http://localhost:8001/nc/folders/permissions" \
	-H "Authorization: Bearer ${TOKEN}" \
	-H "Content-Type: application/json" \
	-d '{"folder_path":"team","subject_type":"user","subject_id":2,"can_read":true,"can_upload":true,"can_manage":false,"apply_existing_files":true}'
```

공유 폴더 쓰기 예시:
- 위처럼 `can_upload=true` 로 폴더를 공유하면, 다른 사용자는 해당 폴더 아래에 하위 폴더를 만들거나 파일을 업로드할 수 있습니다.
- 업로드된 파일은 폴더 소유자 공간에 저장되고, 폴더 권한을 상속받습니다.

공유 폴더 목록:

```bash
curl -X GET "http://localhost:8001/nc/folders/shared" \
	-H "Authorization: Bearer ${TOKEN}"
```

내가 접근 가능한 전체 폴더 목록(내 폴더 + 공유 폴더):

```bash
curl -X GET "http://localhost:8001/nc/folders/accessible" \
	-H "Authorization: Bearer ${TOKEN}"
```

공유 폴더 파일 조회:

```bash
curl -X GET "http://localhost:8001/nc/files?owner_id=1&prefix=team" \
	-H "Authorization: Bearer ${TOKEN}"
```

권한 충돌 우선순위 규칙:
- 동일 subject(user/group/public + subject_id)에 대해 여러 상위 폴더 규칙이 겹치면 파일에 더 가까운(더 깊은) 폴더 규칙이 우선 적용됩니다.

공유받은 파일 목록:

```bash
curl -X GET "http://localhost:8001/nc/files/shared" \
	-H "Authorization: Bearer ${TOKEN}"
```

휴지통 이동/복원:

```bash
curl -X POST "http://localhost:8001/nc/files/1/trash" \
	-H "Authorization: Bearer ${TOKEN}"

curl -X POST "http://localhost:8001/nc/files/1/restore" \
	-H "Authorization: Bearer ${TOKEN}"
```

레거시 API Key 엔드포인트(호환 유지):

파일 업로드:

```bash
curl -X POST "http://localhost:8001/files" \
	-H "x-api-key: ${API_KEY}" \
	-F "file=@./README.md"
```

파일 목록:

```bash
curl -X GET "http://localhost:8001/files" \
	-H "x-api-key: ${API_KEY}"
```

다운로드 URL 발급:

```bash
curl -X GET "http://localhost:8001/files/README.md/download-url" \
	-H "x-api-key: ${API_KEY}"
```

파일 삭제:

```bash
curl -X DELETE "http://localhost:8001/files/README.md" \
	-H "x-api-key: ${API_KEY}"
```

## 6) 실서비스 전환 체크리스트

- 인증/인가
	- 현재는 API Key만 사용
	- 사내 SSO(OIDC/SAML) + RBAC 적용 권장
- 임베딩 모델
	- 현재는 데모용 경량 deterministic embedding
	- 필요 시 `.env`에서 `EMBEDDING_ENABLED=false`로 임베딩 기능 비활성화 가능
	- 실서비스는 사내 표준 임베딩 모델(예: bge, e5, OpenAI compatible)로 교체
- 수집 파이프라인
	- 파일/메일/위키/DB 커넥터
	- 변경분 증분 인덱싱 + 삭제 동기화
- 품질
	- 재랭킹(cross-encoder) 및 하이브리드 검색(BM25 + 벡터)
- 운영
	- OpenTelemetry, 로그 중앙화, 백업/보관 정책, 버킷 수명주기 설정

## 7) 왜 이렇게 구성했나

- FastAPI: 내부 API 확장/운영이 쉽고 Python 생태계 활용 가능
- Milvus: 대량 벡터 검색 성능과 생태계가 안정적
- MinIO: 사내 오브젝트 스토리지 표준으로 운영하기 용이

이 템플릿을 기반으로 다음 단계를 붙이면 완성도 높은 사내 검색 플랫폼으로 확장할 수 있습니다.