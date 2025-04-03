# Code Documentation - Discord NAS Share Bot

This document provides an overview of the codebase structure and the purpose of the main components of the Discord NAS Share Bot project.

## Project Structure Overview

```
.
├── bot/                  # Discord Bot (discord.py)
│   └── bot.py
├── webapp/               # Web Application (Flask)
│   ├── templates/
│   │   └── upload.html   # Upload page template
│   ├── app.py            # Flask routes, upload/download logic
│   └── database.py       # SQLite database interactions
├── uploader/             # NAS Uploader Service (Python Script)
│   └── uploader.py
├── data/                 # Persistent Data (Managed by Docker Volumes)
│   ├── pending_uploads/  # Cache directory for files before NAS upload
│   └── database/         # Directory for SQLite database file
├── .env                  # Configuration (Secrets, URLs, Paths)
├── .gitignore            # Files/directories ignored by Git
├── Dockerfile            # Defines the Docker image for services
├── docker-compose.yml    # Orchestrates the Docker containers
├── requirements.txt      # Python dependencies
├── PLAN.md               # Initial architecture plan
└── README.md             # Setup and usage instructions
```

## Component Explanations

### 1. `bot/bot.py`

- **Framework:** `discord.py` library.
- **Purpose:** Handles all interactions with the Discord API.
- **Key Functions:**
  - Initializes the Discord bot client and connects using the `DISCORD_BOT_TOKEN`.
  - Registers and handles the `/upload` slash command.
  - **`/upload` Command Logic:**
    - Checks if the command is used in an allowed channel (if configured in `.env`).
    - Generates a unique UUID as an upload token.
    - Calls `webapp.database.add_upload_token` to store the token along with the user ID and channel ID, setting an expiry time.
    - Constructs the upload URL using `FLASK_APP_BASE_URL` and the token.
    - Sends an ephemeral Direct Message (DM) to the user containing the upload URL.
  - **Notification Polling (`check_notifications_task`):**
    - Uses `discord.ext.tasks` to run a background loop every 15 seconds (configurable).
    - Calls `webapp.database.get_pending_notifications` to fetch unprocessed notifications.
    - For each notification, calls `send_completion_message`.
    - Calls `webapp.database.delete_notification` to remove the notification after processing.
  - **`send_completion_message`:**
    - Fetches the original Discord channel using the `channel_id` from the notification.
    - Constructs the final download link using `FLASK_APP_BASE_URL` and the `file_id`.
    - Sends a public message to the channel, mentioning the original user (`user_id`) and providing the download link and original filename.
- **Dependencies:** `discord.py`, `python-dotenv`, `webapp.database`.

### 2. `webapp/app.py`

- **Framework:** Flask.
- **Purpose:** Provides the HTTP web interface for file uploads and downloads.
- **Key Functions:**
  - Initializes the Flask application.
  - Loads configuration from `.env` (Secret Key, Base URL, paths).
  - Defines Flask routes:
    - **`/` (Index):** Simple route confirming the web app is running.
    - **`/upload/<token>` (GET):**
      - Validates the `token` by calling `webapp.database.get_token_context`.
      - If valid, renders the `templates/upload.html` template.
      - If invalid/expired, returns a 404 error.
    - **`/upload/<token>` (POST):**
      - Validates the `token`.
      - Retrieves the uploaded file from the request (`request.files['file']`).
      - Generates a unique `file_id` (UUID).
      - Constructs a `cached_path` within the `data/pending_uploads` directory.
      - Saves the uploaded file stream to the `cached_path`.
      - Calls `webapp.database.add_upload_record` to store metadata (file ID, original name, cached path, context, timestamp, status='cached').
      - Calls `webapp.database.add_bot_notification` to queue a notification for the bot.
      - Calls `webapp.database.delete_token` to invalidate the upload token.
      - Returns a simple success message to the browser.
    - **`/download/<file_id>` (GET):**
      - Calls `webapp.database.get_upload_record` to retrieve file metadata using the `file_id`.
      - **Cache Path:** If the record exists, status is 'cached', and the `cached_path` file exists, it serves the file directly from the cache using `send_from_directory`.
      - **NAS Fallback Path (TODO):** If status is 'on_nas', it should connect to the NAS (using details from `.env`) and stream the file from `nas_path`. (Currently returns a placeholder message).
      - Returns 404 if the file record doesn't exist or cannot be served from cache/NAS.
- **Dependencies:** `Flask`, `python-dotenv`, `werkzeug`, `webapp.database`.

### 3. `webapp/database.py`

- **Framework:** Standard Python `sqlite3` module.
- **Purpose:** Manages all interactions with the SQLite database (`metadata.db`). Encapsulates database logic away from the main application/bot code.
- **Key Functions:**
  - `init_db()`: Creates the SQLite database file and the necessary tables (`upload_tokens`, `uploads`, `bot_notifications`) if they don't exist. Called automatically on module import.
  - `get_db()`: Helper function to establish a database connection.
  - **Token Functions:** `add_upload_token`, `get_token_context`, `delete_token`, `cleanup_expired_tokens`.
  - **Upload Metadata Functions:** `add_upload_record`, `get_upload_record`, `update_upload_status`, `get_uploads_by_status`, `delete_upload_record`.
  - **Bot Notification Functions:** `add_bot_notification`, `get_pending_notifications`, `delete_notification`.
- **Dependencies:** `sqlite3`, `datetime`, `os`.

### 4. `uploader/uploader.py`

- **Framework:** Standard Python script using `schedule` and `webdav3` libraries.
- **Purpose:** Runs as a background service to transfer files from the local cache to the NAS.
- **Key Functions:**
  - Loads NAS WebDAV credentials and other configuration from `.env`.
  - `get_webdav_client()`: Initializes the WebDAV client using credentials and checks/creates the base target folder on the NAS.
  - `upload_pending_files()`:
    - Calls `webapp.database.get_uploads_by_status('cached')` to find files needing upload.
    - Iterates through pending files.
    - Updates status to 'uploading_to_nas' in the DB.
    - Uses the WebDAV client's `upload_sync` method to transfer the file from `cached_path` to the `NAS_TARGET_FOLDER` on the NAS.
    - On success, calls `webapp.database.update_upload_status` to set status to 'on_nas' and record the `nas_path`.
    - On failure, logs the error and reverts status to 'cached' for retry.
  - `cleanup_old_cache_files()` **(TODO):** Placeholder for logic to delete files from the cache directory based on age after successful NAS upload.
  - `run_scheduled_tasks()`: Uses the `schedule` library to periodically call `upload_pending_files` based on `UPLOADER_INTERVAL_SECONDS`.
- **Dependencies:** `webdav3`, `python-dotenv`, `schedule`, `webapp.database`.

### 5. Docker Configuration (`Dockerfile`, `docker-compose.yml`)

- **`Dockerfile`:** Defines the common base image for all Python services. It installs Python, copies the code (`bot`, `webapp`, `uploader` directories), installs dependencies from `requirements.txt`, and sets the working directory.
- **`docker-compose.yml`:**
  - Defines three services: `webapp`, `bot`, `uploader`.
  - Specifies that all services should be built using the `Dockerfile` in the current directory (`build: .`).
  - Sets the specific `command` to run for each service (e.g., `python webapp/app.py`).
  - Maps port 5000 for the `webapp` service.
  - Mounts the `.env` file read-only into each container.
  - Defines and mounts named volumes (`cache_data`, `db_data`) to persist the cache and database outside the container lifecycles, ensuring data isn't lost on restart.
  - Sets `restart: unless-stopped` policy for resilience.

This structure separates concerns, making the codebase easier to understand, maintain, and potentially scale in the future.
