import os
import glob
import time
import asyncio
import tempfile
import argparse
import re
import json
from typing import Optional

from telethon import TelegramClient, errors, types
from telethon.tl.types import InputMediaUploadedDocument

from hachoir.parser import createParser
from hachoir.metadata import extractMetadata

from FastTelethonhelper import fast_upload

AUTH_FILE = "auth.json"

async def send_file(
    client: TelegramClient,  # Pass the client as a parameter
    chat_id: int,
    file_path: str,
    description: str,
    topic_id: Optional[int] = None,  # Topic ID
    thumbnail_path: Optional[str] = None,
    progress_message: Optional[types.Message] = None,
):
    """Sends a file to Telegram,
    with support for topic groups and custom thumbnails.
    """
    file_name = os.path.basename(file_path)
    print(file_path)
    file_size = os.path.getsize(file_path)

    # Helper function to format file size
    def format_file_size(size):
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f}KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f}MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f}GB"

    # Helper function to replace variables using regex
    async def format_description(text):  # Make the function asynchronous
        video_resolution = await get_video_resolution_string(
            client, file_path
        )  # Pass the client
        text = re.sub(r"{{\s*fileName\s*}}", file_name, text)
        text = re.sub(
            r"{{\s*fileSize\s*}}", format_file_size(file_size), text
        )
        text = re.sub(r"{{\s*resolution\s*}}", video_resolution, text)
        text = re.sub('\\\\n', '\n', text)
        return text

    # Format the description (awaiting the coroutine)
    description = await format_description(description)

    # Helper function to display progress in the console and return the formatted string
    def progress_callback(current, total):
        current_mb = current / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        progress_str = f'Progress: {current_mb:.2f}MB/{total_mb:.2f}MB'
        print(progress_str, end='\r')
        return progress_str  # Return the progress string

    # Determine media type based on file extension
    if file_path.endswith(('.png', '.jpg', '.jpeg', '.gif')):
        media_type = 'photo'
    elif file_path.endswith('.mp4'):
        media_type = 'video'
    else:
        media_type = 'document'

    # Define thumbnail based on arguments
    if thumbnail_path and media_type in ('video', 'document'):
        # Use custom image if provided
        if is_valid_image(thumbnail_path):
            thumbnail = await client.upload_file(
                thumbnail_path, file_name='thumbnail.jpg'
            )
        else:
            print(
                "Warning: Invalid image path. Using default thumbnail (if applicable)."
            )
            thumbnail = None
    elif media_type == 'video':
        # Try to extract thumbnail from video using ffmpeg
        with tempfile.TemporaryDirectory() as temp_dir:
            thumbnail_path = os.path.join(temp_dir, 'thumbnail.jpg')
            await extract_video_thumb(file_path, thumbnail_path)
            thumbnail = (
                await client.upload_file(thumbnail_path, file_name='thumbnail.jpg')
                if os.path.exists(thumbnail_path)
                else None
            )
    else:
        thumbnail = None

    # Get video resolution (if it's a video)
    video_width, video_height = await get_video_resolution(
        client, file_path
    )  # Pass the client

    # Create media object to be sent
    if media_type == 'video':
        media = InputMediaUploadedDocument(
            file=await fast_upload(
                client,
                file_path,
                progress_message,
                file_name,
                progress_callback,
            ),
            thumb=thumbnail,
            mime_type='video/mp4',
            attributes=[
                types.DocumentAttributeVideo(
                    duration=await get_video_duration(
                        client, file_path
                    ),  # Pass the client
                    w=video_width,  # Set video width
                    h=video_height,  # Set video height
                    round_message=False,
                    supports_streaming=True,
                )
            ],
        )
    elif media_type == 'document':
        media = InputMediaUploadedDocument(
            file=await fast_upload(
                client,
                file_path,
                progress_message,
                file_name,
                progress_callback,
            ),
            attributes=[
                types.DocumentAttributeFilename(file_name=file_name)
            ],
            mime_type='application/octet-stream',
        )
    else:
        media = InputMediaUploadedDocument(
            file=await fast_upload(
                client,
                file_path,
                progress_message,
                file_name,
                progress_callback,
            ),
            mime_type='image/*',  # Define mimetype for images
        )

    # Send the file directly to the topic
    message = await client.send_file(
        chat_id,
        media,
        caption=description,
        parse_mode='Markdown',
        reply_to=topic_id,  # Set topic ID
        force_document=media_type == 'document',
    )

    return message


async def get_video_duration(client: TelegramClient, file_path: str) -> int:  # Pass the client
    """Gets the duration of a video in seconds."""
    try:
        parser = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata and metadata.has('duration'):
            return int(metadata.get('duration').seconds)
    except Exception as e:
        print(f"Error getting video duration: {e}")
    return 0


async def get_video_resolution(client: TelegramClient, file_path: str) -> tuple:
    """Gets the resolution of a video."""
    try:
        parser = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata and metadata.has('width') and metadata.has('height'):
            return int(metadata.get('width')), int(metadata.get('height'))
    except Exception as e:
        print(f"Error getting video resolution: {e}")
    return 1920, 1080  # Return a default resolution in case of error



async def get_video_resolution_string(
    client: TelegramClient, file_path: str
) -> str:  # Pass the client
    """Gets the resolution of a video in string format (ex: 720p)."""
    width, height = await get_video_resolution(
        client, file_path
    )  # Pass the client

    if width >= 3840 and height >= 2160:
        return "2160p"
    elif width >= 1920 and height >= 1080:
        return "1080p"
    elif width >= 1280 and height >= 720:
        return "720p"
    elif width >= 854 and height >= 480:
        return "480p"
    else:
        return "SD"


def is_valid_image(image_path: str) -> bool:
    """Checks if a file is a valid image (PNG, JPEG, JPG)."""
    return image_path.endswith(('.png', '.jpeg', '.jpg'))


async def extract_video_thumb(file_path: str, thumbnail_path: str) -> None:
    """Extracts a frame from a video as a thumbnail."""
    if not file_path.endswith(
        ('.mp4', '.mkv')
    ):  # Check the file extension
        return

    try:
        process = await asyncio.create_subprocess_exec(
            'ffmpeg',
            '-i',
            file_path,
            '-ss',
            '00:00:01',
            '-vframes',
            '1',
            thumbnail_path,
        )
        await process.communicate()
    except Exception as e:
        print(f"Error extracting video thumbnail: {e}")


def load_auth_data():
    """Loads authentication data from the auth.json file."""
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    return None


def save_auth_data(api_id, api_hash):
    """Saves authentication data to the auth.json file."""
    data = {"api_id": api_id, "api_hash": api_hash}
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f)


async def check_auth(client: TelegramClient):  # Pass the client
    """Checks if authentication is valid."""
    try:
        await client.get_me()
        return True
    except errors.rpcerrorlist.UnauthorizedError:
        return False

async def main():
    parser = argparse.ArgumentParser(
        description="Sends files to a Telegram group."
    )
    parser.add_argument(
        '-p', '--path', type=str, help='Folder containing files to upload'
    )
    parser.add_argument(
        '-f', '--file', type=str, help='Path to a single file'
    )
    parser.add_argument(
        '-c', '--chat', type=int, help='Chat ID of the destination'
    )
    parser.add_argument(
        '-t', '--topic', type=int, help='Chat topic ID (optional)'
    )
    parser.add_argument(
        '-d',
        '--description',
        type=str,
        default='',
        help='Description for the file(s) (optional)',
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Delete files after upload (optional)',
    )
    parser.add_argument(
        '-i',
        '--image',
        type=str,
        help='Path to a custom thumbnail image (optional)',
    )
    parser.add_argument(
        '--logout', action='store_true', help='Logs out (deletes auth.json)'
    )
    parser.add_argument(
        '--login',
        nargs=2,
        metavar=('api_id', 'api_hash'),
        help='Logs in with provided api_id and api_hash',
    )
    parser.add_argument(
        '--isLogged', action='store_true', help='Checks if logged in'
    )
    args = parser.parse_args()

    if args.isLogged:
        print(os.path.exists(AUTH_FILE))
        exit(0)

    if args.logout:
        if os.path.exists(AUTH_FILE):
            os.remove(AUTH_FILE)
            for session_file in glob.glob("*.session"):
                os.remove(session_file)
            print("Logout successful!")
        else:
            print("You are already logged out.")
        exit(0)

    if args.login:
        api_id, api_hash = args.login
        # Initialize the client here, with authentication data from the --login argument
        client = TelegramClient('my_session', api_id, api_hash)
        await client.start()
        if await check_auth(client):
            save_auth_data(api_id, api_hash)
            print("Login successful!")
        else:
            print("Error: Invalid credentials.")
            exit(1)

    # Load authentication data from file or prompt the user
    auth_data = load_auth_data()
    if not auth_data:
        print('Go to https://my.telegram.org/ to get your credentials.')
        api_id = input("Enter your api_id: ")
        api_hash = input("Enter your api_hash: ")
        # Initialize the client here, with authentication data provided by the user
        client = TelegramClient('my_session', api_id, api_hash)
        await client.start() # Start the client before checking authentication
        if await check_auth(client):
            save_auth_data(api_id, api_hash)
            print("Login successful!")
        else:
            print("Error: Invalid credentials.")
            exit(1)
    else:
        # Initialize the client here, with authentication data from the auth.json file
        client = TelegramClient('my_session', auth_data["api_id"], auth_data["api_hash"])
        await client.start() # Start the client before checking authentication
        if not await check_auth(client):
            print("Invalid session. Logging out.")
            os.remove(AUTH_FILE)
            # Request new authentication data
            api_id = input("Enter your api_id: ")
            api_hash = input("Enter your api_hash: ")
            # Initialize the client here, with authentication data provided by the user
            client = TelegramClient('my_session', api_id, api_hash)
            await client.start() # Start the client before checking authentication
            if await check_auth(client):
                save_auth_data(api_id, api_hash)
                print("Login successful!")
            else:
                print("Error: Invalid credentials.")
                exit(1)

    chat_id = args.chat
    folder_path = args.path
    file_path = args.file
    topic_id = args.topic
    description = args.description
    clear_files = args.clear
    thumbnail_path = args.image

    # Start the client
    await client.start()

    if folder_path:
        for file_name in glob.glob(os.path.join(folder_path, '*')):
            progress_message = await client.send_message(
                chat_id,
                f"Sending file: {file_name}",
                reply_to=topic_id,
            )
            try:
                await send_file(
                    client,  # Pass the client to the function
                    chat_id,
                    file_name,
                    description,
                    topic_id,
                    thumbnail_path,
                    progress_message,
                )
                if clear_files:
                    os.remove(file_name)
            finally:
                await client.delete_messages(chat_id, progress_message)
    elif file_path:
        progress_message = await client.send_message(
            chat_id,
            f"Sending file: {file_path}",
            reply_to=topic_id,
        )
        try:
            await send_file(
                client,  # Pass the client to the function
                chat_id,
                file_path,
                description,
                topic_id,
                thumbnail_path,
                progress_message,
            )
            if clear_files:
                os.remove(file_path)
        finally:
            await client.delete_messages(chat_id, progress_message)
    else:
        print("You must specify a file or folder using -f or -p.")


if __name__ == '__main__':
    asyncio.run(main())