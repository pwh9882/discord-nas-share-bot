# Discord NAS Share Bot

This project provides a Discord bot and associated web services to allow users to upload files larger than Discord's limit directly to a Network Attached Storage (NAS) device via a web interface. The bot generates a temporary upload link, the user uploads the file via their browser, and the bot posts a shareable download link back to the Discord channel.

Files are initially cached on the server running the application for faster access and then asynchronously uploaded to the NAS using WebDAV.

## Features

- **Discord Slash Command:** `/upload` command to initiate the file upload process.
- **Web Upload Interface:** Simple browser-based interface for uploading large files.
- **Temporary Cache:** Files are cached locally on the server for quick initial uploads and downloads.
- **Asynchronous NAS Upload:** Files are transferred from the cache to the NAS in the background via WebDAV.
- **Download Links:** Generates links to download the uploaded files (served from cache initially, NAS fallback planned).
- **Dockerized:** Uses Docker and Docker Compose for easy deployment and management.
- **Configurable:** Settings managed via a `.env` file.

## Project Structure

```
.
├── bot/                  # Discord Bot code
│   └── bot.py
├── webapp/               # Flask Web Application code
│   ├── templates/
│   │   └── upload.html   # HTML template for the upload page
│   ├── app.py            # Main Flask application logic (routes, upload/download handling)
│   └── database.py       # SQLite database interaction logic
├── uploader/             # NAS Uploader Service code
│   └── uploader.py
├── data/                 # Persistent data (mounted via Docker volumes)
│   ├── pending_uploads/  # Local cache for uploaded files
│   └── database/         # SQLite database file(s)
├── .env                  # Environment variables (Credentials, Tokens, Config) - **DO NOT COMMIT**
├── .gitignore            # Git ignore rules
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose service orchestration
├── requirements.txt      # Python dependencies
├── PLAN.md               # Architecture plan document
└── README.md             # This file
```

## Setup and Installation

1. **Prerequisites:**

   - Docker installed ([https://docs.docker.com/get-docker/](https://docs.docker.com/get-docker/))
   - Docker Compose installed ([https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/))
   - A Discord Bot Application created ([https://discord.com/developers/applications](https://discord.com/developers/applications)) with a Bot Token.
   - A NAS device accessible via WebDAV from the server where this application will run. You'll need the WebDAV URL, a username, and a password.
   - (Optional but Recommended) A domain name pointing to the server running this application, especially if accessing from outside your local network.

2. **Clone the Repository:**

   ```bash
   git clone <your-repository-url>
   cd discord-nas-share-bot
   ```

3. **Configure Environment Variables:**

   - Copy or rename `.env.example` (if provided) to `.env`, or create `.env` manually.
   - Edit the `.env` file and fill in **all** the required values:
     - `DISCORD_BOT_TOKEN`: Your Discord bot's token.
     - `DISCORD_TARGET_CHANNEL_IDS` (Optional): Comma-separated list of Discord Channel IDs where the `/upload` command should be allowed. Leave blank to allow in all channels.
     - `FLASK_SECRET_KEY`: A strong, random secret key for Flask sessions. Generate one using `python -c 'import secrets; print(secrets.token_hex(16))'`.
     - `FLASK_APP_BASE_URL`: The public URL where the web application will be accessible (e.g., `http://your-server-ip:5000` or `https://your-domain.com`). **Must be reachable by users.**
     - `FLASK_ADMIN_USERNAME` / `FLASK_ADMIN_PASSWORD` (Optional): Credentials for a future admin interface.
     - `NAS_WEBDAV_URL`: Full URL to your NAS WebDAV endpoint (e.g., `https://mynas.synology.me:5006/webdav`).
     - `NAS_WEBDAV_USER`: Username for WebDAV access.
     - `NAS_WEBDAV_PASS`: Password for WebDAV access.
     - `NAS_TARGET_FOLDER`: The base folder path on your NAS where files will be uploaded (e.g., `/DiscordUploads`).
     - Adjust other settings like `CACHE_DIR`, `DATABASE_PATH`, `UPLOAD_TOKEN_EXPIRY_SECONDS`, `UPLOADER_INTERVAL_SECONDS` if needed (defaults are usually fine).

4. **Build and Run with Docker Compose:**

   ```bash
   docker-compose up --build -d
   ```

   - `--build`: Forces Docker to build the image based on the `Dockerfile`. Needed the first time and after code changes.
   - `-d`: Runs the containers in detached mode (in the background).

5. **Invite Discord Bot:**
   - Go to your Discord Developer Portal application page.
   - Navigate to "OAuth2" -> "URL Generator".
   - Select the scopes: `bot` and `applications.commands`.
   - Select Bot Permissions: `Send Messages`, `Read Message History` (needed to know the channel), potentially `Attach Files` (though not used for the upload itself). Grant other permissions as needed.
   - Copy the generated URL and paste it into your browser.
   - Select the server you want to add the bot to and authorize it.

## Usage

1. In a Discord channel where the bot is present (and allowed, if `DISCORD_TARGET_CHANNEL_IDS` is set), type the slash command:

   ```
   /upload
   ```

2. The bot will reply with an ephemeral message (only visible to you) containing a unique upload link.
3. Click the link. It will open the web upload interface in your browser.
4. Select the file you want to upload and click "Upload".
5. Once the file is successfully uploaded to the server's cache, you'll see a success message in your browser.
6. Shortly after, the Discord bot will post a message in the original channel (visible to everyone) containing the user mention and the final download link.
7. Anyone with the link can click it to download the file.

## Managing the Application

- **View Logs:** `docker-compose logs -f` (add service name like `webapp`, `bot`, or `uploader` to see specific logs).
- **Stop:** `docker-compose down`
- **Restart:** `docker-compose restart` (or restart individual services: `docker-compose restart webapp`)
- **Update:**
  1. `git pull` (to get code changes)
  2. `docker-compose up --build -d` (to rebuild the image and restart containers)

## TODO / Future Improvements

- Implement NAS download fallback in `webapp/app.py`.
- Implement cache cleanup logic in `uploader/uploader.py`.
- Add a proper success page template (`success.html`).
- Implement the Admin Web Interface.
- Improve error handling and user feedback.
- Consider using a more robust notification system than DB polling (e.g., Redis Pub/Sub).
- Switch to a production WSGI server (like Gunicorn) for the Flask app.
- Configure HTTPS (e.g., using a reverse proxy like Nginx or Caddy).
- Add authentication/authorization for download links if needed.
