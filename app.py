import tkinter as tk
from tkinter import ttk
from tkinter import Label
from urllib.parse import urlparse, parse_qs
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import os
import re
import tempfile
import mimetypes
import threading
import webbrowser
import random
import string
import magic

# Declarar variables globales
folder_name = None
failed_urls = []
downloaded_files = 0

# Función para obtener la extensión basada en el tipo MIME
def get_extension_from_mime(mime_type):
    mime_to_extension = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'application/pdf': '.pdf',
        'text/plain': '.txt',
        'application/zip': '.zip',
        'application/vnd.ms-excel': '.xls',
        'application/msword': '.doc',
        'application/octet-stream': '.bin',  # Mantén la extensión .bin si es un binario genérico
        # Agrega más tipos MIME según lo que quieras manejar
    }
    return mime_to_extension.get(mime_type, '.bin')  # Si no se reconoce el tipo, deja .bin

# Función para renombrar archivos binarios según su tipo real
def rename_bin_files(folder_path):
    # Inicializar la herramienta magic para detectar tipos MIME
    mime_detector = magic.Magic(mime=True)
    
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.bin'):
            file_path = os.path.join(folder_path, file_name)
            
            # Detectar el tipo MIME del archivo
            mime_type = mime_detector.from_file(file_path)
            print(f"Archivo: {file_name}, MIME detectado: {mime_type}")
            
            # Obtener la nueva extensión basada en el tipo MIME
            new_extension = get_extension_from_mime(mime_type)
            
            # Renombrar el archivo solo si la extensión cambia
            if not file_name.endswith(new_extension):
                new_file_name = os.path.splitext(file_name)[0] + new_extension
                new_file_path = os.path.join(folder_path, new_file_name)
                
                # Renombrar el archivo
                os.rename(file_path, new_file_path)
                print(f"Renombrado a: {new_file_name}")
            else:
                os.remove(file_path)
                print(f"No se necesita cambiar la extensión para: {file_name}")


# Función para limpiar nombres de carpetas no válidos en Windows
def clean_folder_name(folder_name):
    folder_name = folder_name.strip()
    return re.sub(r'[\\/*?:"<>|]', '_', folder_name)

# Función para extraer URLs
def extract_urls(file_content):
    url_pattern = re.compile(
        r'(https?://(?:www\.)?[a-zA-Z0-9./\-_~:?#[\]@!$&\'()*+,;=]+)'
    )
    return url_pattern.findall(file_content)

# Función para obtener la extensión del archivo basada en el tipo MIME
def get_file_extension(mime_type):
    return mimetypes.guess_extension(mime_type) or '.bin'

# Función para actualizar la barra de progreso
def update_progress_bar(value):
    progress_var.set(value)
    root.update_idletasks()

# Función para cancelar el proceso de descarga
def cancel_download():
    global cancel_flag
    cancel_flag = True
    update_progress_bar(0)
    download_button['state'] = tk.NORMAL
    cancel_button['state'] = tk.DISABLED
    retry_button['state'] = tk.DISABLED
    progress_label.config(text="Descarga cancelada\n")

# Función para reintentar la descarga de archivos
def retry_download():
    retry_button['state'] = tk.DISABLED
    if failed_urls:
        threading.Thread(target=lambda: download_files(failed_urls, folder_name, threading.Event(), retry=True)).start()

# Función para actualizar el botón de reintentar
def update_retry_button(failed_count):
    if failed_count == 0:
        retry_button['text'] = "Reintentar"
        retry_button['state'] = tk.DISABLED
    else:
        retry_button['text'] = f"Reintentar ({failed_count} archivos)"
        retry_button['state'] = tk.NORMAL

# Función para manejar la descarga de imágenes desde Imgur
def download_imgur_image(url, folder_name):
    global downloaded_files
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            # Obtener el nombre del archivo de la URL de Imgur
            file_name = url.split('/')[-1]
            file_path = os.path.join(folder_name, file_name)

            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Imagen descargada desde Imgur: {file_path}")
            downloaded_files += 1
        else:
            print(f"Error al descargar la imagen desde Imgur: {response.status_code}")
            failed_urls.append(url)
    except Exception as e:
        print(f"Error al descargar imagen desde Imgur: {e}")
        failed_urls.append(url)

# Función para manejar la descarga de archivos desde Dropbox
def download_dropbox_file(url, folder_name):
    global downloaded_files
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            # Extraer el nombre del archivo del encabezado 'Content-Disposition'
            content_disposition = response.headers.get('Content-Disposition', '')
            file_name_match = re.findall('filename="(.+)"', content_disposition)

            # Si el encabezado tiene un nombre de archivo, usarlo. Si no, usar un nombre por defecto.
            if file_name_match:
                file_name = file_name_match[0]
            else:
                # Si no se encuentra el nombre, usar el último segmento de la URL
                file_name = url.split('/')[-1]

            # Asegurarse de que el archivo tenga la extensión correcta
            file_path = os.path.join(folder_name, file_name)

            # Descargar el archivo y guardarlo
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Archivo descargado desde Dropbox: {file_path}")
            downloaded_files += 1
        else:
            print(f"Error al descargar el archivo desde Dropbox: {response.status_code}")
            failed_urls.append(url)
    except Exception as e:
        print(f"Error al descargar archivo desde Dropbox: {e}")
        failed_urls.append(url)

# Función para descargar archivos a partir de una lista de URLs
def download_files(urls, folder_name, progress_event, retry=False):
    global cancel_flag, failed_urls, downloaded_files
    total_files = len(urls)
    cancel_flag = False
    failed_urls = []
    downloaded_files = 0
    
    for index, url in enumerate(urls):
        if cancel_flag:
            print("Descarga cancelada.")
            failed_urls.append(url)
            break
        
        # Verificar si es una URL de Imgur
        parsed_url = urlparse(url)
        if "dropbox.com" in parsed_url.netloc:
            # Descargar el archivo desde Dropbox
            download_dropbox_file(url, folder_name)
        elif "imgur.com" in parsed_url.netloc:
            # Descargar la imagen de Imgur
            download_imgur_image(url, folder_name)
        else:
            tmp_url = url.replace('cloud-3.steamusercontent.com', 'steamusercontent-a.akamaihd.net')
            tmp_url = tmp_url.replace('http://', 'https://')

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
            try:
                response = requests.get(tmp_url, headers=headers, stream=True)
                if response.status_code == 200:
                    file_extension = get_file_extension(response.headers.get('Content-Type', ''))
                    if "steamusercontent-a.akamaihd.net" in parsed_url.netloc:
                        file_name = url.split('/')[-2] + file_extension
                    else:
                        file_name = ''.join(random.choices(string.ascii_letters, k=30)) + file_extension
                    file_path = os.path.join(folder_name, file_name)

                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    downloaded_files += 1
                    #print(f"Archivo descargado: {file_path}")
                else:
                    if response.status_code != 404:
                        print(f"Error al descargar el archivo (code {response.status_code}): {tmp_url}")
                        failed_urls.append(url)
            except requests.exceptions.SSLError as ssl_error:
                print(f"Error SSL al descargar {tmp_url}: {ssl_error}")
                failed_urls.append(url)
            except Exception as e:
                print(f"Error al descargar {tmp_url}: {e}")
                failed_urls.append(url)

        progress_label.config(text=f"{folder_name}\nDescargando {downloaded_files}/{total_files}")
        update_progress_bar((index + 1) / total_files * 100)

    if not cancel_flag:
        rename_bin_files(folder_name)
        if failed_urls:
            progress_label.config(text=f"{folder_name}\nDescarga finalizada. {len(failed_urls)} archivos fallidos")
            update_retry_button(len(failed_urls))
        else:
            progress_label.config(text=f"{folder_name}\nDescarga finalizada ({downloaded_files}/{total_files})")
            retry_button['state'] = tk.DISABLED
    else:
        progress_label.config(text="Descarga cancelada\n")
    
    progress_event.set()

def process_download():
    global folder_name
    url = url_entry.get()
    download_button['state'] = tk.DISABLED
    cancel_button['state'] = tk.NORMAL
    retry_button['state'] = tk.DISABLED
    
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    
    if 'id' in query_params:
        workshop_id = query_params['id'][0]
        print(f"Workshop ID: {workshop_id}")

        # URL de la API de Steam Workshop
        url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
        print(f"Descargar de: {url}")

        # Parámetros de la solicitud POST
        data = {
            'itemcount': 1,
            'publishedfileids[0]': workshop_id
        }

        # Realizar la solicitud POST
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return {'error': f'Error en la solicitud: {e}'}

        # Decodificar la respuesta JSON
        decoded_response = response.json()
        
        # Validar la respuesta
        if 'response' in decoded_response and 'publishedfiledetails' in decoded_response['response']:
            response = decoded_response['response']['publishedfiledetails'][0]

            file_url = response['file_url']
            folder_name = response['title']
            folder_name = clean_folder_name(folder_name)

            if not os.path.exists(folder_name):
                os.makedirs(folder_name)
                print(f"Carpeta creada: {folder_name}")

            file_response = requests.get(file_url)
            if file_response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, mode='wb') as temp_file:
                    temp_file.write(file_response.content)
                    temp_file_path = temp_file.name
                    print(f"Archivo temporal descargado: {temp_file_path}")

                with open(temp_file_path, 'rb') as file:
                    file_content = file.read().decode('utf-8', errors='ignore')

                urls = extract_urls(file_content)
                unique_urls = list(set(urls))

                progress_var.set(0)
                progress_bar['value'] = 0

                progress_event = threading.Event()
                download_thread = threading.Thread(target=lambda: download_files(unique_urls, folder_name, progress_event))
                download_thread.start()
                download_thread.join()

                os.remove(temp_file_path)
                print(f"Archivo temporal eliminado: {temp_file_path}")

            else:
                print(f"Error al descargar el archivo: {file_response.status_code}")
        else:
            return {'error': 'Error al obtener los detalles del workshop.'}
    else:
        print("No se pudo extraer el ID de la URL.")

    update_retry_button(len(failed_urls))
    download_button['state'] = tk.NORMAL
    cancel_button['state'] = tk.DISABLED
    update_progress_bar(0)

# Función para manejar el clic en el botón de descarga
def on_download_click():
    progress_label.config(text="Analizando...\n")
    threading.Thread(target=process_download).start()

# Función para abrir el enlace en el navegador
def open_link(event):
    webbrowser.open("https://steamcommunity.com/app/286160/workshop/")

# Crear ventana principal
root = tk.Tk()
root.title("TTS Downloader")
root.geometry("280x250")
root.eval('tk::PlaceWindow . center')
root.resizable(False, False)  # Deshabilitar redimensionamiento

# Establecer el icono
try:
    root.iconbitmap('icon.ico')
except Exception as e:
    print(f"Error al cargar el icono: {e}")

# Crear frame para centrar los elementos
frame = ttk.Frame(root, padding="10 10 10 10")
frame.grid(column=0, row=0, sticky=(tk.W, tk.E, tk.N, tk.S))
frame.columnconfigure(0, weight=1)
frame.rowconfigure(0, weight=1)

# Etiqueta Workshop URL
url_label = ttk.Label(frame, text="Workshop URL:")
url_label.grid(column=0, row=0, padx=5, pady=5, sticky=tk.W)

# Input para URL
url_entry = ttk.Entry(frame, width=40)
url_entry.grid(column=0, row=1, columnspan=2, padx=5, pady=5)

# Botón Descargar
download_button = ttk.Button(frame, text="Descargar", command=on_download_click)
download_button.grid(column=0, row=2, padx=5, pady=5, sticky=tk.W)

# Botón Cancelar
cancel_button = ttk.Button(frame, text="Cancelar", command=cancel_download, state=tk.DISABLED)
cancel_button.grid(column=1, row=2, padx=5, pady=5, sticky=tk.E)

# Botón Reintentar
retry_button = ttk.Button(frame, text="Reintentar", command=retry_download, state=tk.DISABLED)
retry_button.grid(column=0, row=3, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

# Etiqueta de progreso
progress_label = ttk.Label(frame, text="\n", width=40)
progress_label.grid(column=0, row=4, columnspan=2, padx=5, pady=5, sticky=tk.W)

# Barra de progreso
progress_var = tk.DoubleVar()
progress_bar = ttk.Progressbar(frame, variable=progress_var, maximum=100)
progress_bar.grid(column=0, row=5, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

# Enlace en la esquina superior derecha
link_label = tk.Label(root, text="TTS Workshop", fg="blue", cursor="hand2")
link_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.NE)
link_label.bind("<Button-1>", open_link)

# Créditos
credits_label = ttk.Label(root, text="v1.2 | Desarrollado por @Slaytonw", font=("Helvetica", 8))
credits_label.grid(row=1, column=0, pady=0, sticky=tk.S)

# Ejecutar la aplicación
root.mainloop()