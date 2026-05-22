import os
import re
import sys
import random
import string
import mimetypes
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk
from urllib.parse import urlparse, parse_qs

import requests

# --- Constants ---
REQUEST_TIMEOUT = (10, 30)  # (connect, read) seconds
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
HEADERS = {'User-Agent': USER_AGENT}

# --- Shared state ---
cancel_event = threading.Event()
folder_name = None
failed_urls = []
downloaded_files = 0


# --- App / icon path resolution (works both as .py and Nuitka standalone) ---
def app_dir():
    if '__compiled__' in globals() or getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# --- Magic-number sniffing (replaces python-magic / libmagic) ---
MAGIC_SIGNATURES = [
    (b'\xff\xd8\xff', '.jpg'),
    (b'\x89PNG\r\n\x1a\n', '.png'),
    (b'GIF87a', '.gif'),
    (b'GIF89a', '.gif'),
    (b'%PDF', '.pdf'),
    (b'PK\x03\x04', '.zip'),
    (b'ID3', '.mp3'),
    (b'OggS', '.ogg'),
    (b'BM', '.bmp'),
    (b'\x00\x00\x01\x00', '.ico'),
]


def detect_extension(file_path):
    try:
        with open(file_path, 'rb') as f:
            head = f.read(16)
    except OSError:
        return None
    if head.startswith(b'RIFF') and len(head) >= 12:
        if head[8:12] == b'WEBP':
            return '.webp'
        if head[8:12] == b'WAVE':
            return '.wav'
    if len(head) >= 12 and head[4:8] == b'ftyp':
        return '.mp4'
    for sig, ext in MAGIC_SIGNATURES:
        if head.startswith(sig):
            return ext
    return None


def rename_bin_files(folder_path):
    for file_name in os.listdir(folder_path):
        if not file_name.endswith('.bin'):
            continue
        file_path = os.path.join(folder_path, file_name)
        new_ext = detect_extension(file_path)
        if not new_ext or new_ext == '.bin':
            continue
        new_name = os.path.splitext(file_name)[0] + new_ext
        try:
            os.rename(file_path, os.path.join(folder_path, new_name))
        except OSError:
            pass


# --- Helpers ---
def clean_folder_name(name):
    return re.sub(r'[\\/*?:"<>|]', '_', name.strip())


def get_downloads_dir():
    home = os.path.expanduser('~')
    for candidate in (
        os.path.join(home, 'Downloads'),
        os.path.join(home, 'OneDrive', 'Downloads'),
        home,
    ):
        if os.path.isdir(candidate):
            return candidate
    return os.getcwd()


def extract_urls(text):
    pattern = re.compile(r"https?://(?:www\.)?[a-zA-Z0-9./\-_~:?#@!$&'()*+,;=%]+")
    return [u.rstrip('.,);\'"') for u in pattern.findall(text)]


def guess_extension(mime_type):
    return mimetypes.guess_extension(mime_type) or '.bin'


def normalize_dropbox(url):
    if 'dl=0' in url:
        return url.replace('dl=0', 'dl=1')
    if 'dl=' not in url:
        return url + ('&dl=1' if '?' in url else '?dl=1')
    return url


def resolve_imgur(url):
    if 'i.imgur.com' in url:
        return url
    m = re.match(r'https?://(?:www\.)?imgur\.com/([a-zA-Z0-9]+)/?$', url)
    if m:
        return f'https://i.imgur.com/{m.group(1)}.jpg'
    return url


# --- Thread-safe UI updates ---
def ui(fn, *args, **kwargs):
    root.after(0, lambda: fn(*args, **kwargs))


def set_progress(value):
    ui(progress_var.set, value)


def set_status(text):
    ui(progress_label.config, text=text)


def set_buttons(downloading):
    def apply():
        download_button['state'] = tk.DISABLED if downloading else tk.NORMAL
        cancel_button['state'] = tk.NORMAL if downloading else tk.DISABLED
    root.after(0, apply)


def update_retry_button(failed_count):
    def apply():
        if failed_count == 0:
            retry_button['text'] = "Reintentar"
            retry_button['state'] = tk.DISABLED
        else:
            retry_button['text'] = f"Reintentar ({failed_count} archivos)"
            retry_button['state'] = tk.NORMAL
    root.after(0, apply)


# --- Download primitives ---
def write_stream_to_file(response, file_path):
    """Write streamed response to file. Returns False if cancelled mid-download."""
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if cancel_event.is_set():
                return False
            if chunk:
                f.write(chunk)
    return True


def download_generic(url, folder):
    global downloaded_files
    tmp_url = url.replace('cloud-3.steamusercontent.com', 'steamusercontent-a.akamaihd.net')
    tmp_url = tmp_url.replace('http://', 'https://')
    try:
        response = requests.get(tmp_url, headers=HEADERS, stream=True, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        failed_urls.append(url)
        return
    if response.status_code != 200:
        if response.status_code != 404:
            failed_urls.append(url)
        return
    mime = response.headers.get('Content-Type', '').split(';')[0].strip()
    ext = guess_extension(mime)
    if 'steamusercontent-a.akamaihd.net' in urlparse(tmp_url).netloc:
        file_name = url.split('/')[-2] + ext
    else:
        file_name = ''.join(random.choices(string.ascii_letters, k=30)) + ext
    file_path = os.path.join(folder, file_name)
    if write_stream_to_file(response, file_path):
        downloaded_files += 1
    else:
        try:
            os.remove(file_path)
        except OSError:
            pass


def download_imgur(url, folder):
    global downloaded_files
    resolved = resolve_imgur(url)
    try:
        response = requests.get(resolved, headers=HEADERS, stream=True, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        failed_urls.append(url)
        return
    if response.status_code != 200:
        failed_urls.append(url)
        return
    file_name = resolved.split('/')[-1].split('?')[0]
    file_path = os.path.join(folder, file_name)
    if write_stream_to_file(response, file_path):
        downloaded_files += 1


def download_dropbox(url, folder):
    global downloaded_files
    resolved = normalize_dropbox(url)
    try:
        response = requests.get(resolved, headers=HEADERS, stream=True, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        failed_urls.append(url)
        return
    if response.status_code != 200:
        failed_urls.append(url)
        return
    disposition = response.headers.get('Content-Disposition', '')
    match = re.findall(r'filename="(.+?)"', disposition)
    file_name = match[0] if match else resolved.split('/')[-1].split('?')[0]
    file_path = os.path.join(folder, file_name)
    if write_stream_to_file(response, file_path):
        downloaded_files += 1


def download_files(urls, folder, retry=False):
    global failed_urls, downloaded_files
    cancel_event.clear()
    failed_urls = []
    downloaded_files = 0
    total = len(urls)
    label = os.path.basename(folder) or folder

    for i, url in enumerate(urls):
        if cancel_event.is_set():
            break
        netloc = urlparse(url).netloc.lower()
        if 'dropbox.com' in netloc:
            download_dropbox(url, folder)
        elif 'imgur.com' in netloc:
            download_imgur(url, folder)
        else:
            download_generic(url, folder)
        set_status(f"{label}\nDescargando {downloaded_files}/{total}")
        set_progress((i + 1) / total * 100)

    if cancel_event.is_set():
        set_status("Descarga cancelada\n")
    else:
        rename_bin_files(folder)
        if failed_urls:
            set_status(f"{label}\nDescarga finalizada. {len(failed_urls)} fallidos")
        else:
            set_status(f"{label}\nDescarga finalizada ({downloaded_files}/{total})")
        if downloaded_files > 0:
            open_in_explorer(folder)
    update_retry_button(len(failed_urls))
    set_buttons(downloading=False)


def process_download():
    global folder_name
    url = url_entry.get().strip()
    set_buttons(downloading=True)

    params = parse_qs(urlparse(url).query)
    if 'id' not in params:
        set_status("URL no válida\n")
        set_buttons(downloading=False)
        return
    workshop_id = params['id'][0]

    api_url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    try:
        response = requests.post(
            api_url,
            data={'itemcount': 1, 'publishedfileids[0]': workshop_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        details = response.json()['response']['publishedfiledetails'][0]
    except (requests.RequestException, KeyError, IndexError, ValueError):
        set_status("Error consultando Workshop\n")
        set_buttons(downloading=False)
        return

    file_url = details.get('file_url')
    if not file_url:
        set_status("Workshop sin archivo asociado\n")
        set_buttons(downloading=False)
        return

    title = details.get('title') or f'workshop_{workshop_id}'
    folder_name = os.path.join(get_downloads_dir(), clean_folder_name(title))
    os.makedirs(folder_name, exist_ok=True)

    try:
        file_response = requests.get(file_url, timeout=REQUEST_TIMEOUT)
        file_response.raise_for_status()
    except requests.RequestException:
        set_status("Error descargando metadata\n")
        set_buttons(downloading=False)
        return

    content = file_response.content.decode('utf-8', errors='ignore')
    urls = list({u for u in extract_urls(content)})
    if not urls:
        set_status("No se encontraron URLs\n")
        set_buttons(downloading=False)
        return

    set_progress(0)
    download_files(urls, folder_name)


def cancel_download():
    cancel_event.set()


def retry_download():
    if failed_urls and folder_name:
        urls = list(failed_urls)
        retry_button['state'] = tk.DISABLED
        set_buttons(downloading=True)
        threading.Thread(
            target=lambda: download_files(urls, folder_name, retry=True),
            daemon=True,
        ).start()


def on_download_click():
    set_status("Analizando...\n")
    threading.Thread(target=process_download, daemon=True).start()


def open_link(_event):
    webbrowser.open("https://steamcommunity.com/app/286160/workshop/")


def open_in_explorer(path):
    try:
        os.startfile(path)
    except OSError:
        pass


# --- UI ---
root = tk.Tk()
root.title("TTS Downloader")
root.geometry("280x275")
root.eval('tk::PlaceWindow . center')
root.resizable(False, False)

icon_path = os.path.join(app_dir(), 'icon.ico')
if os.path.exists(icon_path):
    try:
        root.iconbitmap(icon_path)
    except tk.TclError:
        pass

frame = ttk.Frame(root, padding="10 10 10 10")
frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))
frame.columnconfigure(0, weight=1)
frame.rowconfigure(0, weight=1)

ttk.Label(frame, text="Workshop URL:").grid(column=0, row=0, padx=5, pady=5, sticky=tk.W)

url_entry = ttk.Entry(frame, width=40)
url_entry.grid(column=0, row=1, columnspan=2, padx=5, pady=5)

hint_label = ttk.Label(
    frame,
    text="Se guardará en tu carpeta Descargas",
    foreground="gray",
    font=("Helvetica", 8, "italic"),
)
hint_label.grid(column=0, row=2, columnspan=2, padx=5, pady=(0, 5), sticky=tk.W)

download_button = ttk.Button(frame, text="Descargar", command=on_download_click)
download_button.grid(column=0, row=3, padx=5, pady=5, sticky=tk.W)

cancel_button = ttk.Button(frame, text="Cancelar", command=cancel_download, state=tk.DISABLED)
cancel_button.grid(column=1, row=3, padx=5, pady=5, sticky=tk.E)

retry_button = ttk.Button(frame, text="Reintentar", command=retry_download, state=tk.DISABLED)
retry_button.grid(column=0, row=4, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

progress_label = ttk.Label(frame, text="\n", width=40)
progress_label.grid(column=0, row=5, columnspan=2, padx=5, pady=5, sticky=tk.W)

progress_var = tk.DoubleVar()
progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100)
progress_bar.grid(column=0, row=6, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

link_label = tk.Label(root, text="TTS Workshop", fg="blue", cursor="hand2")
link_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.NE)
link_label.bind("<Button-1>", open_link)

credits_label = ttk.Label(root, text="v1.4 | Desarrollado por @Slaytonw", font=("Helvetica", 8))
credits_label.grid(row=1, column=0, pady=0, sticky=tk.S)

root.mainloop()
