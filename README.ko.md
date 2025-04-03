# Discord NAS 공유 봇

이 프로젝트는 Discord의 파일 제한보다 큰 파일을 사용자가 웹 인터페이스를 통해 NAS(Network Attached Storage) 장치에 직접 업로드할 수 있도록 지원하는 Discord 봇 및 관련 웹 서비스입니다. 봇은 임시 업로드 링크를 생성하고, 사용자는 브라우저를 통해 파일을 업로드하며, 봇은 공유 가능한 다운로드 링크를 Discord 채널에 다시 게시합니다.

파일은 빠른 접근을 위해 애플리케이션을 실행하는 서버에 먼저 캐시된 후, WebDAV를 사용하여 비동기적으로 NAS에 업로드됩니다.

## 주요 기능

- **Discord 슬래시 명령어:** `/upload` 명령어로 파일 업로드 프로세스 시작.
- **웹 업로드 인터페이스:** 대용량 파일 업로드를 위한 간단한 브라우저 기반 인터페이스.
- **임시 캐시:** 빠른 초기 업로드 및 다운로드를 위해 서버에 로컬로 파일 캐시.
- **비동기 NAS 업로드:** WebDAV를 통해 백그라운드에서 캐시된 파일을 NAS로 전송.
- **다운로드 링크:** 업로드된 파일을 다운로드할 수 있는 링크 생성 (초기에는 캐시에서 제공, NAS 폴백 계획됨).
- **Docker 기반:** Docker 및 Docker Compose를 사용하여 쉬운 배포 및 관리.
- **설정 가능:** `.env` 파일을 통해 설정 관리.

## 프로젝트 구조

```
.
├── bot/                  # Discord 봇 코드
│   └── bot.py
├── webapp/               # Flask 웹 애플리케이션 코드
│   ├── templates/
│   │   └── upload.html   # 업로드 페이지 HTML 템플릿
│   ├── app.py            # 메인 Flask 애플리케이션 로직 (라우트, 업로드/다운로드 처리)
│   └── database.py       # SQLite 데이터베이스 상호작용 로직
├── uploader/             # NAS 업로더 서비스 코드
│   └── uploader.py
├── data/                 # 영구 데이터 (Docker 볼륨으로 마운트)
│   ├── pending_uploads/  # 업로드된 파일 로컬 캐시
│   └── database/         # SQLite 데이터베이스 파일 디렉토리
├── .env                  # 환경 변수 (자격 증명, 토큰, 설정) - **커밋 금지**
├── .gitignore            # Git 무시 규칙
├── Dockerfile            # Docker 이미지 정의
├── docker-compose.yml    # Docker Compose 서비스 오케스트레이션
├── requirements.txt      # Python 의존성
├── PLAN.md               # 아키텍처 계획 문서
└── README.md             # 영문 README 파일
└── README.ko.md          # 이 파일 (한글 README)
```

## 설치 및 설정

1. **사전 요구 사항:**

   - Docker 설치 ([https://docs.docker.com/get-docker/](https://docs.docker.com/get-docker/))
   - Docker Compose 설치 ([https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/))
   - Discord 봇 애플리케이션 생성 ([https://discord.com/developers/applications](https://discord.com/developers/applications)) 및 봇 토큰 발급.
   - 애플리케이션을 실행할 서버에서 WebDAV를 통해 접근 가능한 NAS 장치. WebDAV URL, 사용자 이름, 비밀번호 필요.
   - (선택 사항이지만 권장) 애플리케이션을 실행하는 서버를 가리키는 도메인 이름 (특히 외부 네트워크에서 접근 시).

2. **저장소 복제:**

   ```bash
   git clone <your-repository-url>
   cd discord-nas-share-bot
   ```

3. **환경 변수 설정:**

   - `.env.example` 파일(제공된 경우)을 `.env`로 복사하거나 이름을 바꾸거나, `.env` 파일을 직접 생성합니다.
   - `.env` 파일을 편집하여 **모든** 필수 값을 입력합니다:
     - `DISCORD_BOT_TOKEN`: Discord 봇 토큰.
     - `DISCORD_TARGET_CHANNEL_IDS` (선택 사항): `/upload` 명령어를 허용할 Discord 채널 ID 목록 (쉼표로 구분). 비워두면 모든 채널에서 허용.
     - `FLASK_SECRET_KEY`: Flask 세션을 위한 강력하고 무작위적인 비밀 키. `python -c 'import secrets; print(secrets.token_hex(16))'` 명령어로 생성 가능.
     - `FLASK_APP_BASE_URL`: 웹 애플리케이션에 접근할 수 있는 공개 URL (예: `http://your-server-ip:5000` 또는 `https://your-domain.com`). **사용자가 접근 가능해야 합니다.**
     - `FLASK_ADMIN_USERNAME` / `FLASK_ADMIN_PASSWORD` (선택 사항): 향후 관리자 인터페이스를 위한 자격 증명.
     - `NAS_WEBDAV_URL`: NAS WebDAV 엔드포인트의 전체 URL (예: `https://mynas.synology.me:5006/webdav`).
     - `NAS_WEBDAV_USER`: WebDAV 접근 사용자 이름.
     - `NAS_WEBDAV_PASS`: WebDAV 접근 비밀번호.
     - `NAS_TARGET_FOLDER`: 파일이 업로드될 NAS의 기본 폴더 경로 (예: `/DiscordUploads`).
     - 필요한 경우 `CACHE_DIR`, `DATABASE_PATH`, `UPLOAD_TOKEN_EXPIRY_SECONDS`, `UPLOADER_INTERVAL_SECONDS` 등 다른 설정을 조정합니다 (기본값으로도 충분할 수 있음).

4. **Docker Compose로 빌드 및 실행:**

   ```bash
   docker-compose up --build -d
   ```

   - `--build`: `Dockerfile`을 기반으로 이미지를 강제로 빌드합니다. 처음 실행하거나 코드 변경 후 필요합니다.
   - `-d`: 컨테이너를 백그라운드(detached mode)에서 실행합니다.

5. **Discord 봇 초대:**
   - Discord 개발자 포털의 애플리케이션 페이지로 이동합니다.
   - "OAuth2" -> "URL Generator"로 이동합니다.
   - 스코프 선택: `bot` 및 `applications.commands`.
   - 봇 권한 선택: `Send Messages`, `Read Message History` (채널 확인에 필요), `Attach Files` (업로드 자체에는 사용되지 않음). 필요에 따라 다른 권한 부여.
   - 생성된 URL을 복사하여 브라우저에 붙여넣습니다.
   - 봇을 추가할 서버를 선택하고 승인합니다.

## 사용법

1. 봇이 있고 허용된 Discord 채널에서 (만약 `DISCORD_TARGET_CHANNEL_IDS`가 설정된 경우) 슬래시 명령어를 입력합니다:

   ```
   /upload
   ```

2. 봇이 고유한 업로드 링크가 포함된 임시 메시지(ephemeral, 본인에게만 보임)로 응답합니다.
3. 링크를 클릭하면 브라우저에서 웹 업로드 인터페이스가 열립니다.
4. 업로드할 파일을 선택하고 "Upload"를 클릭합니다.
5. 파일이 서버 캐시에 성공적으로 업로드되면 브라우저에 성공 메시지가 표시됩니다.
6. 잠시 후, Discord 봇이 원래 채널에 사용자 멘션과 최종 다운로드 링크가 포함된 메시지(모든 사용자에게 보임)를 게시합니다.
7. 링크가 있는 사람은 누구나 클릭하여 파일을 다운로드할 수 있습니다.

## 애플리케이션 관리

- **로그 보기:** `docker-compose logs -f` (특정 로그를 보려면 `webapp`, `bot`, `uploader`와 같은 서비스 이름 추가).
- **중지:** `docker-compose down`
- **재시작:** `docker-compose restart` (또는 개별 서비스 재시작: `docker-compose restart webapp`)
- **업데이트:**
  1. `git pull` (코드 변경 사항 가져오기)
  2. `docker-compose up --build -d` (이미지 재빌드 및 컨테이너 재시작)

## TODO / 향후 개선 사항

- `webapp/app.py`에 NAS 다운로드 폴백 기능 구현.
- `uploader/uploader.py`에 캐시 정리 로직 구현.
- 적절한 성공 페이지 템플릿 (`success.html`) 추가.
- 관리자 웹 인터페이스 구현.
- 오류 처리 및 사용자 피드백 개선.
- DB 폴링보다 더 강력한 알림 시스템 고려 (예: Redis Pub/Sub).
- Flask 앱을 위한 프로덕션 WSGI 서버(예: Gunicorn)로 전환.
- HTTPS 설정 (예: Nginx 또는 Caddy와 같은 리버스 프록시 사용).
- 필요한 경우 다운로드 링크에 대한 인증/권한 부여 추가.
