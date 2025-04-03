import os
import sys
import time
import logging
from webdav3.client import Client
from dotenv import load_dotenv
import schedule  # Using schedule library for simplicity, can be replaced by cron in Docker

# Add the parent directory to sys.path to allow importing webapp.database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import webapp.database as db
except ImportError:
    print("Error: Could not import database module. Make sure it's accessible.")
    sys.exit(1)

# --- Configuration ---
load_dotenv(dotenv_path="../.env")

# NAS WebDAV Config
NAS_WEBDAV_URL = os.getenv("NAS_WEBDAV_URL")
NAS_WEBDAV_USER = os.getenv("NAS_WEBDAV_USER")
NAS_WEBDAV_PASS = os.getenv("NAS_WEBDAV_PASS")
NAS_TARGET_FOLDER = os.getenv("NAS_TARGET_FOLDER", "/DiscordUploads").strip(
    "/"
)  # Ensure no leading/trailing slashes initially

# App Config
CACHE_DIR = os.path.abspath(os.getenv("CACHE_DIR", "../data/pending_uploads"))
UPLOADER_INTERVAL_SECONDS = int(os.getenv("UPLOADER_INTERVAL_SECONDS", 600))
CACHE_CLEANUP_AGE_DAYS = int(
    os.getenv("CACHE_CLEANUP_AGE_DAYS", 7)
)  # 0 or negative means no cleanup

# Basic Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("nas_uploader")


# --- WebDAV Client Setup ---
def get_webdav_client():
    """Creates and returns a configured WebDAV client."""
    if not all([NAS_WEBDAV_URL, NAS_WEBDAV_USER, NAS_WEBDAV_PASS]):
        logger.error("WebDAV credentials not fully configured in .env file.")
        return None
    options = {
        "webdav_hostname": NAS_WEBDAV_URL,
        "webdav_login": NAS_WEBDAV_USER,
        "webdav_password": NAS_WEBDAV_PASS,
        # Add other options if needed, e.g., cert verification path
        # 'webdav_cert_path': '/path/to/cert'
    }
    try:
        client = Client(options)
        # Check connection / create base directory if needed
        if not client.is_dir(NAS_TARGET_FOLDER):
            logger.info(
                f"Base NAS target folder '{NAS_TARGET_FOLDER}' not found, attempting to create."
            )
            try:
                client.mkdir(NAS_TARGET_FOLDER)
                logger.info(f"Created base NAS folder: {NAS_TARGET_FOLDER}")
            except Exception as mkdir_err:
                logger.error(
                    f"Failed to create base NAS folder '{NAS_TARGET_FOLDER}': {mkdir_err}"
                )
                return None  # Cannot proceed if base folder cannot be created
        return client
    except Exception as e:
        logger.error(f"Failed to initialize WebDAV client: {e}", exc_info=True)
        return None


# --- Core Upload Logic ---
def upload_pending_files():
    """Checks DB for 'cached' files and uploads them to NAS."""
    logger.info("Starting pending file upload check...")
    pending_files = db.get_uploads_by_status("cached")

    if not pending_files:
        logger.info("No pending files found.")
        return

    logger.info(f"Found {len(pending_files)} file(s) pending upload.")
    client = get_webdav_client()
    if not client:
        logger.error("Cannot proceed with uploads: WebDAV client not available.")
        return

    for file_record in pending_files:
        file_id = file_record["file_id"]
        cached_path = file_record["cached_path"]
        original_filename = file_record["original_filename"]
        # Construct remote path, maybe include year/month subfolders?
        # Example: /DiscordUploads/2025/04/file_id_original.ext
        # For simplicity now, just use file_id + original name
        remote_filename = f"{file_id}_{original_filename}"
        remote_path = (
            f"{NAS_TARGET_FOLDER}/{remote_filename}"  # webdavclient3 handles joining
        )

        logger.info(
            f"Attempting to upload {file_id} ({original_filename}) from {cached_path} to {remote_path}"
        )

        if not os.path.exists(cached_path):
            logger.error(
                f"Cached file not found for {file_id}: {cached_path}. Setting status to 'error'."
            )
            db.update_upload_status(file_id, "error")
            continue

        try:
            # Update status to 'uploading' before starting
            db.update_upload_status(file_id, "uploading_to_nas")
            logger.debug(f"Set status to 'uploading_to_nas' for {file_id}")

            # Perform the upload
            client.upload_sync(remote_path=remote_path, local_path=cached_path)
            logger.info(f"Successfully uploaded {file_id} to {remote_path}")

            # Update status to 'on_nas' and store nas_path
            db.update_upload_status(file_id, "on_nas", nas_path=remote_path)
            logger.info(f"Updated status to 'on_nas' for {file_id}")

            # Optional: Cleanup cache immediately or based on policy
            # if CACHE_CLEANUP_AGE_DAYS == 0: # Immediate cleanup
            #     try:
            #         os.remove(cached_path)
            #         logger.info(f"Removed file from cache: {cached_path}")
            #     except OSError as e:
            #         logger.error(f"Error removing cached file {cached_path}: {e}")

        except Exception as e:
            logger.error(f"Failed to upload {file_id} to NAS: {e}", exc_info=True)
            # Revert status to 'cached' for retry later? Or set to 'error'?
            # Let's revert to 'cached' for now to allow retries.
            db.update_upload_status(file_id, "cached")
            logger.warning(
                f"Reverted status to 'cached' for {file_id} after upload failure."
            )

    logger.info("Finished pending file upload check.")


# --- TODO: Cache Cleanup Logic ---
def cleanup_old_cache_files():
    """Removes files from cache that are 'on_nas' and older than policy."""
    if CACHE_CLEANUP_AGE_DAYS <= 0:
        logger.info("Cache cleanup based on age is disabled.")
        return

    logger.info(
        f"Starting cache cleanup (policy: older than {CACHE_CLEANUP_AGE_DAYS} days)..."
    )
    # 1. Get files with status 'on_nas' from DB
    # 2. For each file, check its upload_timestamp
    # 3. If timestamp is older than CACHE_CLEANUP_AGE_DAYS
    # 4. And if the cached_path exists
    # 5. Delete the file from cache (os.remove(cached_path))
    # 6. Consider updating the DB record to remove cached_path? (Optional)
    logger.warning("Cache cleanup logic not yet implemented.")
    pass


# --- Scheduler ---
def run_scheduled_tasks():
    """Runs the main tasks according to the schedule."""
    schedule.every(UPLOADER_INTERVAL_SECONDS).seconds.do(upload_pending_files)
    # schedule.every().day.at("03:00").do(cleanup_old_cache_files) # Example: Run cleanup daily at 3 AM

    logger.info(
        f"Scheduler started. Upload check interval: {UPLOADER_INTERVAL_SECONDS} seconds."
    )
    upload_pending_files()  # Run once immediately on start

    while True:
        schedule.run_pending()
        time.sleep(1)


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting NAS Uploader Service...")
    # Perform initial DB check/init (already done on import, but good practice)
    db.init_db()
    run_scheduled_tasks()
