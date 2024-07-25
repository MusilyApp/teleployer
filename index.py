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
    client: TelegramClient,  # Passar o cliente como parâmetro
    chat_id: int,
    file_path: str,
    description: str,
    topic_id: Optional[int] = None,  # ID do tópico
    thumbnail_path: Optional[str] = None,
    progress_message: Optional[types.Message] = None,
):
    """Envia um arquivo para o Telegram,
    com suporte a grupos com tópicos e thumbnails personalizadas.
    """
    file_name = os.path.basename(file_path)
    print(file_path)
    file_size = os.path.getsize(file_path)

    # Função auxiliar para formatar o tamanho do arquivo
    def format_file_size(size):
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f}KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f}MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f}GB"

    # Função auxiliar para substituir as variáveis usando regex
    async def format_description(text):  # Tornar a função assíncrona
        video_resolution = await get_video_resolution_string(
            client, file_path
        )  # Passar o cliente
        text = re.sub(r"{{\s*fileName\s*}}", file_name, text)
        text = re.sub(
            r"{{\s*fileSize\s*}}", format_file_size(file_size), text
        )
        text = re.sub(r"{{\s*resolution\s*}}", video_resolution, text)
        text = re.sub('\\\\n', '\n', text)
        return text

    # Formata a descrição (aguardando a coroutine)
    description = await format_description(description)

    # Função auxiliar para exibir o progresso no console e retornar a string formatada
    def progress_callback(current, total):
        current_mb = current / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        progress_str = f'Progresso: {current_mb:.2f}MB/{total_mb:.2f}MB'
        print(progress_str, end='\r')
        return progress_str  # Retorna a string de progresso

    # Determina o tipo de mídia com base na extensão do arquivo
    if file_path.endswith(('.png', '.jpg', '.jpeg', '.gif')):
        media_type = 'photo'
    elif file_path.endswith('.mp4'):
        media_type = 'video'
    else:
        media_type = 'document'

    # Define a miniatura com base nos argumentos
    if thumbnail_path and media_type in ('video', 'document'):
        # Usa a imagem personalizada se fornecida
        if is_valid_image(thumbnail_path):
            thumbnail = await client.upload_file(
                thumbnail_path, file_name='thumbnail.jpg'
            )
        else:
            print(
                "Aviso: Caminho de imagem inválido. Usando a miniatura padrão (se aplicável)."
            )
            thumbnail = None
    elif media_type == 'video':
        # Tenta extrair a miniatura do vídeo com ffmpeg
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

    # Obtém a resolução do vídeo (se for um vídeo)
    video_width, video_height = await get_video_resolution(
        client, file_path
    )  # Passar o cliente

    # Cria o objeto de mídia a ser enviado
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
                    ),  # Passar o cliente
                    w=video_width,  # Define a largura do vídeo
                    h=video_height,  # Define a altura do vídeo
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
            mime_type='image/*',  # Define o mimetype para imagens
        )

    # Envia o arquivo diretamente para o tópico
    message = await client.send_file(
        chat_id,
        media,
        caption=description,
        parse_mode='Markdown',
        reply_to=topic_id,  # Define o ID do tópico
        force_document=media_type == 'document',
    )

    return message


async def get_video_duration(client: TelegramClient, file_path: str) -> int:  # Passar o cliente
    """Obtém a duração de um vídeo em segundos."""
    try:
        parser = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata and metadata.has('duration'):
            return int(metadata.get('duration').seconds)
    except Exception as e:
        print(f"Erro ao obter a duração do vídeo: {e}")
    return 0


async def get_video_resolution(client: TelegramClient, file_path: str) -> tuple:
    """Obtém a resolução de um vídeo."""
    try:
        parser = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata and metadata.has('width') and metadata.has('height'):
            return int(metadata.get('width')), int(metadata.get('height'))
    except Exception as e:
        print(f"Erro ao obter a resolução do vídeo: {e}")
    return 1920, 1080  # Retorna uma resolução padrão em caso de erro



async def get_video_resolution_string(
    client: TelegramClient, file_path: str
) -> str:  # Passar o cliente
    """Obtém a resolução de um vídeo em formato de string (ex: 720p)."""
    width, height = await get_video_resolution(
        client, file_path
    )  # Passar o cliente

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
    """Verifica se um arquivo é uma imagem válida (PNG, JPEG, JPG)."""
    return image_path.endswith(('.png', '.jpeg', '.jpg'))


async def extract_video_thumb(file_path: str, thumbnail_path: str) -> None:
    """Extrai um frame de um vídeo como miniatura."""
    if not file_path.endswith(
        ('.mp4', '.mkv')
    ):  # Verifica a extensão do arquivo
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
        print(f"Erro ao extrair a miniatura do vídeo: {e}")


def load_auth_data():
    """Carrega os dados de autenticação do arquivo auth.json."""
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    return None


def save_auth_data(api_id, api_hash):
    """Salva os dados de autenticação no arquivo auth.json."""
    data = {"api_id": api_id, "api_hash": api_hash}
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f)


async def check_auth(client: TelegramClient):  # Passar o cliente
    """Verifica se a autenticação é válida."""
    try:
        await client.get_me()
        return True
    except errors.rpcerrorlist.UnauthorizedError:
        return False

async def main():
    parser = argparse.ArgumentParser(
        description="Envia arquivos para um grupo do Telegram."
    )
    parser.add_argument(
        '-p', '--path', type=str, help='Pasta com os arquivos para upload'
    )
    parser.add_argument(
        '-f', '--file', type=str, help='Caminho para um único arquivo'
    )
    parser.add_argument(
        '-c', '--chat', type=int, help='ID do chat de destino'
    )
    parser.add_argument(
        '-t', '--topic', type=int, help='ID do tópico do chat (opcional)'
    )
    parser.add_argument(
        '-d',
        '--description',
        type=str,
        default='',
        help='Descrição para o(s) arquivo(s) (opcional)',
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Apagar arquivos após o upload (opcional)',
    )
    parser.add_argument(
        '-i',
        '--image',
        type=str,
        help='Caminho para a imagem de thumbnail personalizada (opcional)',
    )
    parser.add_argument(
        '--logout', action='store_true', help='Faz logout (apaga auth.json)'
    )
    parser.add_argument(
        '--login',
        nargs=2,
        metavar=('api_id', 'api_hash'),
        help='Faz login com api_id e api_hash fornecidos',
    )
    parser.add_argument(
        '--isLogged', action='store_true', help='Verifica se está logado'
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
            print("Logout efetuado com sucesso!")
        else:
            print("Você já está deslogado.")
        exit(0)

    if args.login:
        api_id, api_hash = args.login
        # Inicializar o cliente aqui, com os dados de autenticação do argumento --login
        client = TelegramClient('my_session', api_id, api_hash)
        await client.start()
        if await check_auth(client):
            save_auth_data(api_id, api_hash)
            print("Login efetuado com sucesso!")
        else:
            print("Erro: Credenciais inválidas.")
            exit(1)

    # Carrega dados de autenticação do arquivo ou solicita ao usuário
    auth_data = load_auth_data()
    if not auth_data:
        print('Acesse https://my.telegram.org/ para conseguir suas credenciais.')
        api_id = input("Digite seu api_id: ")
        api_hash = input("Digite seu api_hash: ")
        # Inicializar o cliente aqui, com os dados de autenticação fornecidos pelo usuário
        client = TelegramClient('my_session', api_id, api_hash)
        await client.start() # Iniciar o cliente antes de verificar a autenticação
        if await check_auth(client):
            save_auth_data(api_id, api_hash)
            print("Login efetuado com sucesso!")
        else:
            print("Erro: Credenciais inválidas.")
            exit(1)
    else:
        # Inicializar o cliente aqui, com os dados de autenticação do arquivo auth.json
        client = TelegramClient('my_session', auth_data["api_id"], auth_data["api_hash"])
        await client.start() # Iniciar o cliente antes de verificar a autenticação
        if not await check_auth(client):
            print("Sessão inválida. Fazendo logout.")
            os.remove(AUTH_FILE)
            # Solicita novos dados de autenticação
            api_id = input("Digite seu api_id: ")
            api_hash = input("Digite seu api_hash: ")
            # Inicializar o cliente aqui, com os dados de autenticação fornecidos pelo usuário
            client = TelegramClient('my_session', api_id, api_hash)
            await client.start() # Iniciar o cliente antes de verificar a autenticação
            if await check_auth(client):
                save_auth_data(api_id, api_hash)
                print("Login efetuado com sucesso!")
            else:
                print("Erro: Credenciais inválidas.")
                exit(1)

    chat_id = args.chat
    folder_path = args.path
    file_path = args.file
    topic_id = args.topic
    description = args.description
    clear_files = args.clear
    thumbnail_path = args.image

    # Inicia o cliente
    await client.start()

    if folder_path:
        for file_name in glob.glob(os.path.join(folder_path, '*')):
            progress_message = await client.send_message(
                chat_id,
                f"Enviando arquivo: {file_name}",
                reply_to=topic_id,
            )
            try:
                await send_file(
                    client,  # Passar o cliente para a função
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
            f"Enviando arquivo: {file_path}",
            reply_to=topic_id,
        )
        try:
            await send_file(
                client,  # Passar o cliente para a função
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
        print("Você deve especificar um arquivo ou pasta usando -f ou -p.")


if __name__ == '__main__':
    asyncio.run(main())