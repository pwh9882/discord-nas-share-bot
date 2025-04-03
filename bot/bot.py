import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import uuid
import logging
from dotenv import load_dotenv
import sys

# Add the parent directory to sys.path to allow importing webapp.database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import webapp.database as db
except ImportError:
    print("Error: Could not import database module. Make sure it's accessible.")
    sys.exit(1)

# --- Configuration ---
load_dotenv(dotenv_path="../.env")  # Load .env from parent directory

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
APP_BASE_URL = os.getenv("FLASK_APP_BASE_URL")
TARGET_CHANNEL_IDS_STR = os.getenv("DISCORD_TARGET_CHANNEL_IDS")
TARGET_CHANNEL_IDS = (
    set(int(id_str.strip()) for id_str in TARGET_CHANNEL_IDS_STR.split(","))
    if TARGET_CHANNEL_IDS_STR
    else None
)

if not BOT_TOKEN:
    print("Error: DISCORD_BOT_TOKEN not found in .env file.")
    sys.exit(1)
if not APP_BASE_URL:
    print("Error: FLASK_APP_BASE_URL not found in .env file.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("discord_bot")

# --- Bot Setup ---
intents = discord.Intents.default()
# No special intents needed for slash commands usually, but add if required later
# intents.message_content = True # Example if needed

bot = commands.Bot(
    command_prefix="!", intents=intents
)  # Prefix not really used for slash commands


# --- Helper Functions ---
def generate_upload_token():
    """Generates a unique upload token."""
    return str(uuid.uuid4())


# --- Events ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"Flask App Base URL: {APP_BASE_URL}")
    if TARGET_CHANNEL_IDS:
        logger.info(f"Restricting /upload command to channel IDs: {TARGET_CHANNEL_IDS}")
    else:
        logger.info("/upload command is available in all channels.")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
    # Start the background task
    check_notifications_task.start()


# --- Slash Commands ---
@bot.tree.command(
    name="upload", description="Generates a link to upload a file to the NAS."
)
@app_commands.checks.cooldown(
    1, 10, key=lambda i: (i.guild_id, i.user.id)
)  # Cooldown: 1 use per 10 sec per user
async def upload_command(interaction: discord.Interaction):
    """Handles the /upload command."""
    user_id = interaction.user.id
    channel_id = interaction.channel_id

    # Check if command is used in an allowed channel (if configured)
    if TARGET_CHANNEL_IDS and channel_id not in TARGET_CHANNEL_IDS:
        await interaction.response.send_message(
            "Sorry, you can only use this command in specific channels.", ephemeral=True
        )
        logger.warning(
            f"/upload blocked for user {user_id} in channel {channel_id} (not allowed)."
        )
        return

    logger.info(
        f"/upload command used by {interaction.user.name} (ID: {user_id}) in channel {channel_id}"
    )

    # 1. Generate Token
    token = generate_upload_token()

    # 2. Store Token and Context in DB
    context = {"user_id": user_id, "channel_id": channel_id}
    if db.add_upload_token(token, context):
        logger.info(f"Generated and stored upload token {token} for user {user_id}")

        # 3. Construct Upload URL
        upload_url = f"{APP_BASE_URL.rstrip('/')}/upload/{token}"

        # 4. Reply to User (Ephemeral)
        message_content = (
            f"Click the link below to upload your file.\n"
            f"This link is valid for a limited time and can only be used once.\n\n"
            f"<{upload_url}>"
        )
        await interaction.response.send_message(message_content, ephemeral=True)
        logger.info(f"Sent upload link to user {user_id}")

    else:
        logger.error(f"Failed to store upload token for user {user_id}")
        await interaction.response.send_message(
            "Sorry, something went wrong generating your upload link. Please try again later.",
            ephemeral=True,
        )


@upload_command.error
async def upload_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """Handles errors for the /upload command."""
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"You're using this command too quickly! Please wait {error.retry_after:.1f} seconds.",
            ephemeral=True,
        )
    else:
        logger.error(f"Error in /upload command: {error}", exc_info=True)
        await interaction.response.send_message(
            "An unexpected error occurred. Please try again later.", ephemeral=True
        )


# --- Bot Notification Handling ---
# Implemented using database polling via a background task.
# Let's plan for Flask to store the completed upload info, and we'll add a mechanism
# for the bot to be triggered later (maybe Flask writes to a simple queue file the bot watches?).


async def send_completion_message(
    channel_id: int, user_id: int, file_id: str, original_filename: str
):
    """Sends the final share link back to the original channel."""
    try:
        # Ensure IDs are integers
        channel_id_int = int(channel_id)
        user_id_int = int(user_id)

        channel = await bot.fetch_channel(channel_id_int)
        if channel:
            share_link = f"{APP_BASE_URL.rstrip('/')}/download/{file_id}"
            user_mention = f"<@{user_id_int}>"
            message = f"{user_mention} Your file '{original_filename}' has been uploaded successfully!\nDownload link: <{share_link}>"
            await channel.send(message)
            logger.info(
                f"Sent completion message for file {file_id} to channel {channel_id_int}"
            )
        else:
            logger.error(
                f"Could not find channel {channel_id_int} to send completion message."
            )
    except discord.NotFound:
        logger.error(f"Channel {channel_id_int} not found.")
    except discord.Forbidden:
        logger.error(
            f"Bot lacks permissions to send message in channel {channel_id_int}."
        )
    except Exception as e:
        logger.error(
            f"Error sending completion message for file {file_id}: {e}", exc_info=True
        )


# --- Background Task for Notifications ---
@tasks.loop(seconds=15)  # Check every 15 seconds
async def check_notifications_task():
    """Periodically checks the database for pending notifications and processes them."""
    # logger.debug("Checking for pending notifications...") # Too noisy for INFO level
    notifications = db.get_pending_notifications()
    if not notifications:
        # logger.debug("No pending notifications found.")
        return

    logger.info(f"Found {len(notifications)} pending notification(s). Processing...")
    for notification in notifications:
        notif_id = notification["notification_id"]
        file_id = notification["file_id"]
        channel_id = notification["channel_id"]
        user_id = notification["user_id"]
        original_filename = notification["original_filename"]

        logger.info(f"Processing notification {notif_id} for file {file_id}...")
        try:
            await send_completion_message(
                channel_id, user_id, file_id, original_filename
            )
            # If sending succeeded, delete the notification
            if db.delete_notification(notif_id):
                logger.info(
                    f"Successfully processed and deleted notification {notif_id}."
                )
            else:
                logger.error(
                    f"Failed to delete notification {notif_id} after processing."
                )
        except Exception as e:
            logger.error(
                f"Error processing notification {notif_id} for file {file_id}: {e}",
                exc_info=True,
            )
            # Decide if we should delete the notification anyway or leave it for retry?
            # Leaving it might cause spam if the error persists. Deleting loses the notification.
            # For now, let's delete it to avoid spam loop. Consider adding retry logic later.
            db.delete_notification(notif_id)
            logger.warning(
                f"Deleted notification {notif_id} after processing error to prevent loop."
            )


@check_notifications_task.before_loop
async def before_check_notifications():
    """Ensures the bot is ready before starting the task loop."""
    await bot.wait_until_ready()
    logger.info("Bot is ready. Starting notification check task.")


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting Discord Bot...")
    # The task is started in on_ready after command sync
    bot.run(BOT_TOKEN)
