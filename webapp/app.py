import os
import uuid
import logging
from datetime import datetime, timezone  # Removed timedelta
from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    send_from_directory,
    abort,
    flash,
    # Removed make_response
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import webapp.database as db  # Import the database module

# --- Configuration ---
load_dotenv(dotenv_path="../.env")  # Load .env from parent directory

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "default-secret-key")
# Use absolute paths for consistency, especially within Docker
app.config["UPLOAD_FOLDER"] = os.path.abspath(
    os.getenv("CACHE_DIR", "../data/pending_uploads")
)
app.config["DATABASE_PATH"] = os.path.abspath(
    os.getenv("DATABASE_PATH", "../data/database/metadata.db")
)
app.config["APP_BASE_URL"] = os.getenv("FLASK_APP_BASE_URL", "http://localhost:5000")
# UPLOAD_TOKEN_EXPIRY_SECONDS is now primarily used in database.py

# Ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
# Database is initialized in database.py when imported

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
app.logger.setLevel(logging.INFO)

# --- Helper Functions ---
# Removed old is_token_valid and invalidate_token - using db module now


def generate_file_id():
    """Generates a unique ID for the file."""
    return str(uuid.uuid4())


# --- Routes ---
@app.route("/")
def index():
    return "Web App is Running!"  # Simple index page


@app.route("/upload/<string:token>", methods=["GET", "POST"])
def upload_file(token):
    context = db.get_token_context(token)
    if not context:
        app.logger.warning(f"Invalid or expired token used: {token}")
        abort(404, description="Invalid or expired upload link.")

    if request.method == "POST":
        # --- Handle File Upload ---
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        if file:
            original_filename = secure_filename(file.filename)
            file_id = generate_file_id()
            # Use file_id or a portion of it to avoid collisions, maybe add timestamp
            cached_filename = f"{file_id}_{original_filename}"
            cached_path = os.path.join(app.config["UPLOAD_FOLDER"], cached_filename)

            try:
                # Get file size and content type before saving if possible, or after
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)  # Reset cursor position
                content_type = file.content_type

                file.save(cached_path)
                app.logger.info(f"File saved to cache: {cached_path}")

                # Store metadata in the database
                if db.add_upload_record(
                    file_id,
                    original_filename,
                    cached_path,
                    context,
                    content_type,
                    file_size,
                ):
                    app.logger.info(f"Upload record added for file_id: {file_id}")
                else:
                    app.logger.error(
                        f"Failed to add upload record for file_id: {file_id}"
                    )
                    # Consider cleanup and error message
                    flash("Database error occurred.")
                    # Maybe remove the saved file? os.remove(cached_path)
                    return redirect(request.url)

                # Add notification for the bot to process
                if db.add_bot_notification(file_id, context, original_filename):
                    app.logger.info(
                        f"Added notification for bot for file_id: {file_id}"
                    )
                else:
                    # Log an error, but maybe don't fail the whole upload?
                    # The bot might pick it up later if it polls the main uploads table.
                    app.logger.error(
                        f"Failed to add bot notification for file_id: {file_id}"
                    )

                share_link = url_for(
                    "download_file", file_id=file_id, _external=True
                )  # Keep for potential success page
                app.logger.info(
                    f"Generated share link: {share_link}"
                )  # Log for debugging
                # Invalidate the token after successful upload
                db.delete_token(token)
                app.logger.info(f"Upload token invalidated: {token}")

                # TODO: Return a proper success page template render_template('success.html', share_link=share_link)
                return f"Upload Successful! File ID: {file_id}. Share link will be sent to Discord shortly."

            except Exception as e:
                app.logger.error(
                    f"Error saving file {original_filename} for token {token}: {e}",
                    exc_info=True,
                )
                flash(f"An error occurred during upload: {e}")
                # Consider cleaning up partially saved file if necessary
                if os.path.exists(cached_path):
                    try:
                        os.remove(cached_path)
                        app.logger.info(
                            f"Cleaned up partially saved file: {cached_path}"
                        )
                    except OSError as rm_err:
                        app.logger.error(
                            f"Error cleaning up file {cached_path}: {rm_err}"
                        )
                return redirect(request.url)

    # --- Serve Upload Form (GET Request) ---
    # --- Serve Upload Form (GET Request) ---
    return render_template("upload.html", token=token)


@app.route("/download/<string:file_id>")
def download_file(file_id):
    app.logger.info(f"Download request received for file_id: {file_id}")
    record = db.get_upload_record(file_id)

    if not record:
        app.logger.warning(f"Download request for non-existent file_id: {file_id}")
        abort(404, description="File not found.")

    # Convert Row to dict for easier access
    metadata = dict(record)
    app.logger.debug(f"Metadata found for {file_id}: {metadata}")

    # Primary serving path: From cache
    if (
        metadata.get("status") == "cached"
        and metadata.get("cached_path")
        and os.path.exists(metadata["cached_path"])
    ):
        app.logger.info(f"Serving file {file_id} from cache: {metadata['cached_path']}")
        try:
            return send_from_directory(
                directory=os.path.dirname(metadata["cached_path"]),
                path=os.path.basename(metadata["cached_path"]),
                as_attachment=True,
                download_name=metadata.get(
                    "original_filename", file_id
                ),  # Use original filename
            )
        except Exception as e:
            app.logger.error(
                f"Error serving cached file {file_id} from {metadata['cached_path']}: {e}",
                exc_info=True,
            )
            abort(500, description="Error serving file from cache.")

    # Fallback path: From NAS
    elif metadata.get("status") == "on_nas" and metadata.get("nas_path"):
        nas_path = metadata["nas_path"]
        app.logger.info(
            f"File {file_id} not in cache. Attempting fallback from NAS path: {nas_path}"
        )
        # TODO: Implement NAS connection (WebDAV/API) and streaming
        # Example (pseudo-code):
        # try:
        #     nas_client = connect_to_nas() # Get configured NAS client
        #     file_stream = nas_client.download_stream(nas_path)
        #     response = make_response(file_stream)
        #     response.headers.set('Content-Type', metadata.get('content_type', 'application/octet-stream'))
        #     response.headers.set('Content-Disposition', 'attachment', filename=metadata.get('original_filename', file_id))
        #     return response
        # except Exception as e:
        #     app.logger.error(f"Error streaming file {file_id} from NAS path {nas_path}: {e}", exc_info=True)
        #     abort(500, description="Error retrieving file from storage.")
        return f"File {file_id} is on NAS at {nas_path} (NAS fallback streaming not implemented yet)."

    # If neither cached nor on NAS (or status is unexpected)
    app.logger.warning(
        f"File {file_id} is in status '{metadata.get('status')}' and cannot be served."
    )
    abort(404, description="File not found or is still processing.")


# --- Main Execution ---
if __name__ == "__main__":
    # Ensure DB is initialized (in case database.py wasn't imported elsewhere first)
    db.init_db()
    # Start a background thread or scheduler for cleanup? (Optional here, maybe better in uploader script)
    # db.cleanup_expired_tokens() # Run once on startup

    # Note: Debug mode should be OFF in production! Use a proper WSGI server like Gunicorn.
    app.logger.info("Starting Flask development server...")
    app.run(
        debug=True, host="0.0.0.0", port=5000
    )  # Listen on all interfaces for Docker
