# 코드 문서 - Discord NAS 공유 봇

이 문서는 Discord NAS 공유 봇 프로젝트의 코드베이스 구조와 주요 구성 요소의 목적에 대한 개요를 제공합니다.

## 프로젝트 구조 개요

```
.
├── bot/                  # Discord 봇 (discord.py)
│   └── bot.py
├── webapp/               # 웹 애플리케이션 (Flask)
│   ├── templates/
│   │   └── upload.html   # 업로드 페이지 템플릿
│   ├── app.py            # Flask 라우트, 업로드/다운로드 로직
│   └── database.py       # SQLite 데이터베이스 상호작용
├── uploader/             # NAS 업로더 서비스 (Python 스크립트)
│   └── uploader.py
├── data/                 # 영구 데이터 (Docker 볼륨으로 관리)
│   ├── pending_uploads/  # NAS 업로드 전 파일 캐시 디렉토리
│   └── database/         # SQLite 데이터베이스 파일 디렉토리
├── .env                  # 설정 (비밀 정보, URL, 경로)
├── .gitignore            # Git 무시 파일/디렉토리
├── Dockerfile            # 서비스용 Docker 이미지 정의
├── docker-compose.yml    # Docker 컨테이너 오케스트레이션
├── requirements.txt      # Python 의존성
├── PLAN.md               # 초기 아키텍처 계획
├── README.md             # 설정 및 사용법 (영문)
└── CODE_DOCUMENTATION.md # 코드 문서 (영문)
└── CODE_DOCUMENTATION.ko.md # 이 파일 (한글 코드 문서)
```

## 구성 요소 설명

### 1. `bot/bot.py`

- **프레임워크:** `discord.py` 라이브러리.
- **목적:** Discord API와의 모든 상호작용 처리.
- **주요 기능:**
  - `DISCORD_BOT_TOKEN`을 사용하여 Discord 봇 클라이언트 초기화 및 연결.
  - `/upload` 슬래시 명령어 등록 및 처리.
  - **`/upload` 명령어 로직:**
    - 명령어가 허용된 채널에서 사용되었는지 확인 (`.env` 설정 기반).
    - 업로드 토큰으로 고유 UUID 생성.
    - `webapp.database.add_upload_token` 호출하여 토큰, 사용자 ID, 채널 ID 저장 및 만료 시간 설정.
    - `FLASK_APP_BASE_URL`과 토큰을 사용하여 업로드 URL 구성.
    - 사용자에게 업로드 URL이 포함된 임시 다이렉트 메시지(DM) 전송.
  - **알림 폴링 (`check_notifications_task`):**
    - `discord.ext.tasks`를 사용하여 15초마다 백그라운드 루프 실행 (설정 가능).
    - `webapp.database.get_pending_notifications` 호출하여 처리되지 않은 알림 가져오기.
    - 각 알림에 대해 `send_completion_message` 호출.
    - 처리 후 `webapp.database.delete_notification` 호출하여 알림 제거.
  - **`send_completion_message`:**
    - 알림의 `channel_id`를 사용하여 원본 Discord 채널 가져오기.
    - `FLASK_APP_BASE_URL`과 `file_id`를 사용하여 최종 다운로드 링크 구성.
    - 원본 사용자(`user_id`)를 멘션하고 다운로드 링크 및 원본 파일 이름을 제공하는 공개 메시지를 채널에 전송.
- **의존성:** `discord.py`, `python-dotenv`, `webapp.database`.

### 2. `webapp/app.py`

- **프레임워크:** Flask.
- **목적:** 파일 업로드 및 다운로드를 위한 HTTP 웹 인터페이스 제공.
- **주요 기능:**
  - Flask 애플리케이션 초기화.
  - `.env`에서 설정 로드 (비밀 키, 기본 URL, 경로).
  - Flask 라우트 정의:
    - **`/` (인덱스):** 웹 앱이 실행 중임을 확인하는 간단한 라우트.
    - **`/upload/<token>` (GET):**
      - `webapp.database.get_token_context`를 호출하여 `token` 유효성 검사.
      - 유효하면 `templates/upload.html` 템플릿 렌더링.
      - 유효하지 않거나 만료되었으면 404 오류 반환.
    - **`/upload/<token>` (POST):**
      - `token` 유효성 검사.
      - 요청에서 업로드된 파일 가져오기 (`request.files['file']`).
      - 고유 `file_id` (UUID) 생성.
      - `data/pending_uploads` 디렉토리 내에 `cached_path` 구성.
      - 업로드된 파일 스트림을 `cached_path`에 저장.
      - `webapp.database.add_upload_record` 호출하여 메타데이터 저장 (파일 ID, 원본 이름, 캐시 경로, 컨텍스트, 타임스탬프, 상태='cached').
      - `webapp.database.add_bot_notification` 호출하여 봇 알림 대기열에 추가.
      - `webapp.database.delete_token` 호출하여 업로드 토큰 무효화.
      - 브라우저에 간단한 성공 메시지 반환.
    - **`/download/<file_id>` (GET):**
      - `webapp.database.get_upload_record` 호출하여 `file_id`를 사용하여 파일 메타데이터 검색.
      - **캐시 경로:** 레코드가 존재하고, 상태가 'cached'이며, `cached_path` 파일이 존재하면 `send_from_directory`를 사용하여 캐시에서 직접 파일 제공.
      - **NAS 폴백 경로 (TODO):** 상태가 'on_nas'이면 NAS에 연결(`.env` 상세 정보 사용)하여 `nas_path`에서 파일 스트리밍해야 함. (현재는 플레이스홀더 메시지 반환).
      - 파일 레코드가 없거나 캐시/NAS에서 제공할 수 없으면 404 반환.
- **의존성:** `Flask`, `python-dotenv`, `werkzeug`, `webapp.database`.

### 3. `webapp/database.py`

- **프레임워크:** 표준 Python `sqlite3` 모듈.
- **목적:** SQLite 데이터베이스(`metadata.db`)와의 모든 상호작용 관리. 데이터베이스 로직을 주 애플리케이션/봇 코드로부터 분리.
- **주요 기능:**
  - `init_db()`: SQLite 데이터베이스 파일 및 필요한 테이블(`upload_tokens`, `uploads`, `bot_notifications`)이 없으면 생성. 모듈 임포트 시 자동으로 호출됨.
  - `get_db()`: 데이터베이스 연결을 설정하는 헬퍼 함수.
  - **토큰 함수:** `add_upload_token`, `get_token_context`, `delete_token`, `cleanup_expired_tokens`.
  - **업로드 메타데이터 함수:** `add_upload_record`, `get_upload_record`, `update_upload_status`, `get_uploads_by_status`, `delete_upload_record`.
  - **봇 알림 함수:** `add_bot_notification`, `get_pending_notifications`, `delete_notification`.
- **의존성:** `sqlite3`, `datetime`, `os`.

### 4. `uploader/uploader.py`

- **프레임워크:** `schedule` 및 `webdav3` 라이브러리를 사용하는 표준 Python 스크립트.
- **목적:** 로컬 캐시에서 NAS로 파일을 전송하는 백그라운드 서비스로 실행.
- **주요 기능:**
  - `.env`에서 NAS WebDAV 자격 증명 및 기타 설정 로드.
  - `get_webdav_client()`: 자격 증명을 사용하여 WebDAV 클라이언트 초기화 및 NAS의 기본 대상 폴더 확인/생성.
  - `upload_pending_files()`:
    - `webapp.database.get_uploads_by_status('cached')` 호출하여 업로드 필요한 파일 찾기.
    - 보류 중인 파일 반복 처리.
    - DB에서 상태를 'uploading_to_nas'로 업데이트.
    - WebDAV 클라이언트의 `upload_sync` 메서드를 사용하여 `cached_path`에서 NAS의 `NAS_TARGET_FOLDER`로 파일 전송.
    - 성공 시 `webapp.database.update_upload_status` 호출하여 상태를 'on_nas'로 설정하고 `nas_path` 기록.
    - 실패 시 오류 기록 및 재시도를 위해 상태를 'cached'로 되돌림.
  - `cleanup_old_cache_files()` **(TODO):** 성공적인 NAS 업로드 후 경과 시간에 따라 캐시 디렉토리에서 파일을 삭제하는 로직 플레이스홀더.
  - `run_scheduled_tasks()`: `schedule` 라이브러리를 사용하여 `UPLOADER_INTERVAL_SECONDS`에 따라 주기적으로 `upload_pending_files` 호출.
- **의존성:** `webdav3`, `python-dotenv`, `schedule`, `webapp.database`.

### 5. Docker 설정 (`Dockerfile`, `docker-compose.yml`)

- **`Dockerfile`:** 모든 Python 서비스를 위한 공통 기본 이미지 정의. Python 설치, 코드(`bot`, `webapp`, `uploader` 디렉토리) 복사, `requirements.txt`에서 의존성 설치, 작업 디렉토리 설정.
- **`docker-compose.yml`:**
  - 세 가지 서비스 정의: `webapp`, `bot`, `uploader`.
  - 모든 서비스가 현재 디렉토리의 `Dockerfile`을 사용하여 빌드되도록 지정 (`build: .`).
  - 각 서비스에 대해 실행할 특정 `command` 설정 (예: `python webapp/app.py`).
  - `webapp` 서비스에 대해 포트 5000 매핑.
  - `.env` 파일을 각 컨테이너에 읽기 전용으로 마운트.
  - 명명된 볼륨(`cache_data`, `db_data`)을 정의하고 마운트하여 컨테이너 라이프사이클 외부에서 캐시 및 데이터베이스를 유지하여 재시작 시 데이터 손실 방지.
  - 복원력을 위해 `restart: unless-stopped` 정책 설정.

이 구조는 관심사를 분리하여 코드베이스를 이해하고 유지 관리하며 향후 확장하기 쉽게 만듭니다.
