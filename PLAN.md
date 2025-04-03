# Discord NAS Share Bot - Architecture Plan

## 1. Overview

This document outlines the architecture for a Discord bot system that allows users to upload files larger than Discord's limit. Files are initially uploaded to a cache on an Oracle A1 instance via a web interface, then asynchronously transferred to a NAS. The bot provides a shareable link that serves the file primarily from the A1 cache, with a fallback to fetch from the NAS if the cached version is unavailable.

## 2. Core Components

The system consists of the following containerized services, managed via Docker Compose:

1. **Discord Bot (Python/discord.py):**

   - Runs on the A1 instance.
   - Listens for an `/upload` slash command in designated Discord channels.
   - Generates a unique, single-use upload token.
   - Stores the original interaction context (user ID, channel ID) associated with the token.
   - Direct Messages (DMs) the user an upload URL (`https://<your_a1_domain>/upload/<token>`).
   - Receives notifications (e.g., via internal API call or message queue) from the Web Application upon successful upload, containing the final sharing link.
   - Posts the sharing link back to the original Discord channel.

2. **Web Application (Python/Flask):**

   - Runs on the A1 instance, serving HTTP requests.
   - **Upload Endpoint (`/upload/<token>` GET/POST):**
     - `GET`: Validates the token, serves a simple HTML upload form.
     - `POST`: Validates the token, receives the file stream, saves it to a temporary cache directory on the A1 instance's local storage (e.g., `/data/pending_uploads/`). Generates a unique _file ID_. Stores metadata (file ID, original filename, cached path, NAS path (initially null), status='cached', timestamps, original context). Constructs the initial sharing link (`https://<your_a1_domain>/download/<file_id>`). Notifies the Discord bot service. Returns a success message to the user. Invalidates the upload token.
   - **Download Endpoint (`/download/<file_id>` GET):**
     - Looks up the `file_id` in metadata.
     - **Primary Path:** If `status` indicates the file is in the A1 cache (`cached_path` exists), serves it directly using `send_file`.
     - **Fallback Path:** If the file is not in cache but `status` is 'on_nas' and `nas_path` is set, attempts to fetch the file from the NAS (using WebDAV/API) and streams it to the user.
     - Returns 404 or other appropriate error if the file is unavailable.
   - **(Optional) Internal API:** Endpoint for communication between web app and bot.

3. **NAS Uploader Service (Python Script):**

   - Runs periodically (e.g., cron job within a container or scheduled task).
   - Scans the metadata store for files with `status == 'cached'`.
   - For each file: Updates status to `'uploading_to_nas'`, connects to NAS (WebDAV/API), uploads the file from A1 cache (`cached_path`).
   - On success: Updates metadata (`nas_path`, `status='on_nas'`). Optionally deletes the file from A1 cache based on a cleanup policy.
   - On failure: Logs error, potentially reverts status or implements retry logic.

4. **Admin Web Interface (Flask Blueprint):**

   - Integrated into the main Flask app, accessible via a specific route (e.g., `/admin`).
   - Requires authentication.
   - Provides a dashboard to view file status, logs, cache usage, etc.
   - May allow manual triggering of NAS sync or cache cleanup.

5. **Docker Setup (`docker-compose.yml`):**
   - Defines services: `discord-bot`, `web-app`, `nas-uploader`.
   - Manages environment variables/secrets (Tokens, Credentials, Domain, Paths).
   - Defines persistent volumes for cache (`/data/pending_uploads`) and metadata (`/data/database`).
   - Configures inter-container networking if needed.

## 3. Workflow Diagram

```mermaid
graph TD
    subgraph User Interaction
        A[User: /upload in Discord Channel] --> B{Discord Bot};
        B --> C[Generate Upload Token];
        C --> D[Store Context (User, Channel)];
        D --> E[DM User: Upload Link (<a1_url>/upload/token)];
        F[User: Clicks Link, Opens Browser];
        F --> G{Web App: Upload UI};
        H[User: Selects File, Submits];
        H --> I{Web App: Handle POST};
        I --> J[Return Success Page];
        K[Bot: Posts Share Link (<a1_url>/download/file_id) to Channel];
        L[Other Users: Click Share Link];
        L --> M{Web App: Handle Download};
        M --> N[Serve File (from A1 Cache or NAS)];
    end

    subgraph A1 Instance Processing
        I --> P[Save File to A1 Cache (/data/pending_uploads)];
        P --> Q[Generate File ID];
        Q --> R[Store Metadata (DB/File)];
        R --> S[Construct Share Link (<a1_url>/download/file_id)];
        S --> T[Notify Bot Service];
        T --> B;

        M --> U{Lookup File ID};
        U -- File in Cache? --> V[Serve from A1 Cache];
        V --> N;
        U -- File NOT in Cache --> W{File on NAS?};
        W -- Yes --> X{Fetch from NAS via WebDAV/API};
        X --> Y[Stream File to User];
        Y --> N;
        W -- No --> Z[Return Error 404];
        Z --> N;
    end

    subgraph A1 Background Tasks
        AA[NAS Uploader Service (Periodic)] --> BB{Scan Metadata for Status='cached'};
        BB -- Found File --> CC[Update Status: 'uploading'];
        CC --> DD{Connect to NAS};
        DD --> EE[Upload File from Cache];
        EE -- Success --> FF[Update Metadata: Set nas_path, Status='on_nas'];
        FF --> GG[Optional: Delete from A1 Cache];
        EE -- Failure --> HH[Log Error, Revert Status?];
    end

    subgraph Admin Interaction
        II[Admin: Accesses /admin] --> M;
        M --> JJ[Show Dashboard, Logs, etc.];
    end

    subgraph External Systems
        KK[Your NAS]
    end

    I --> P;
    T --> B;
    K --> L;
    V --> N;
    Y --> N;
    Z --> N;
    DD --> KK;
    X --> KK;
    GG --> P;
```

## 4. Key Features & Considerations

- **Caching:** Leverages faster A1 instance storage for initial uploads and downloads.
- **Asynchronous NAS Upload:** Decouples user upload from the potentially slower NAS transfer.
- **Fallback Mechanism:** Ensures files remain accessible even after being cleared from the A1 cache.
- **Dockerized:** Simplifies deployment and dependency management.
- **Scalability:** Primarily limited by A1 instance resources (CPU, RAM, storage, network) and NAS performance.
- **Security:** Requires careful handling of tokens, NAS credentials, and potential authentication for the admin interface. HTTPS is essential.
- **State Management:** Metadata storage (SQLite recommended) is crucial for tracking file status and locations.
- **Error Handling:** Robust error handling is needed for network issues, NAS connection problems, disk space limits, etc.
- **Cache Cleanup:** A strategy is needed to prevent the A1 cache from filling up (e.g., delete after successful NAS upload + grace period).

## 5. Technology Stack (Recommended)

- **Language:** Python 3.x
- **Discord Bot:** `discord.py` (or `interactions.py`)
- **Web Framework:** Flask
- **NAS Interaction:** `webdavclient3` (for WebDAV) or `requests` (for NAS API)
- **Metadata Storage:** SQLite (via `sqlite3` module)
- **Containerization:** Docker, Docker Compose
- **Environment Variables:** `python-dotenv`
