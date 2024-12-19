import os
import pandas as pd
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from user_manager import UserManager
import async_timeout
import asyncio
import csv
import time
from concurrent.futures import ThreadPoolExecutor
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram.error import TelegramError
import aiohttp

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))
OWNER_USERNAME = os.getenv('OWNER_USERNAME')

# Initialize user manager
user_manager = UserManager()

# Constants for file operations
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output_vcf"
INPUT_DIR = "input_files"

# Error messages
ERROR_MESSAGES = {
    "access_denied": "Anda tidak memiliki akses ke bot ini. Hubungi admin @{} untuk mendapatkan akses bot",
    "file_too_large": "File terlalu besar. Maksimal ukuran file adalah {}MB.",
    "download_timeout": "Waktu unduh habis. Silakan coba lagi dengan file yang lebih kecil.",
    "processing_error": "Maaf, terjadi kesalahan saat memproses file. Admin telah diberitahu.",
    "unsupported_format": "Format file tidak didukung.",
    "empty_filename": "Nama file tidak boleh kosong. Silakan masukkan nama file lagi."
}

# Constants
MAX_DOWNLOAD_TIMEOUT = 300  # 5 minutes timeout for downloads
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
FILE_UPLOAD_TIMEOUT = 60  # 1 minute timeout for file uploads

# Create necessary directories
for directory in [DOWNLOAD_DIR, OUTPUT_DIR, INPUT_DIR, 'data']:
    os.makedirs(directory, exist_ok=True)

# Log user interactions
LOG_FILE = os.path.join('data', 'usage_log.csv')

# Ensure log file exists
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['timestamp', 'user_id', 'username', 'command', 'message'])

async def log_interaction(update: Update, command: str):
    user_id = update.effective_user.id
    username = update.effective_user.username
    message = update.message.text if update.message else ''
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    
    with open(LOG_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, user_id, username, command, message])

# State definitions for ConversationHandler
ASK_PATTERN, ASK_SPLIT, ASK_SPLIT_SIZE, ASK_SEQUENCE, ASK_FILENAME = range(5)
CREATE_TXT_MESSAGE, CREATE_TXT_FILENAME = range(5, 7)
UPLOAD_VCF_FILES, ASK_VCF_FILENAME = range(7, 9)

def check_whitelist(user_id: int) -> bool:
    """Check if user is whitelisted and has remaining access"""
    if not user_manager.is_whitelisted(user_id):
        return False
    limit = user_manager.get_access_limit(user_id)
    return limit is not None and limit > 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/start')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text(
        "Halo! Pilih fitur yang ingin Anda gunakan:\n"
        "- /txt_to_vcf: Konversi file .txt ke .vcf\n"
        "- /excel_to_vcf: Konversi file .xlsx ke .vcf\n"
        "- /create_txt: Buat file txt dari pesan\n"
        "- /merge_vcf: Gabungkan file .vcf\n"
        "- /checklimit: Cek sisa limit Anda\n"
        "Silakan ketik salah satu perintah untuk memulai.\n"
        "nb: Bot ini masih dalam tahap pengembangan. Jika Anda mengalami kesulitan, silakan hubungi admin @{}.".format(OWNER_USERNAME)
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/getid')
    user_id = update.effective_user.id
    await update.message.reply_text(f"ID Anda adalah: {user_id}")

async def checklimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/checklimit')
    user_id = update.effective_user.id
    limit = user_manager.get_access_limit(user_id)
    
    if limit is None:
        await update.message.reply_text("Anda tidak memiliki batas akses yang ditetapkan.")
    else:
        await update.message.reply_text(f"Batas akses Anda tersisa: {limit}")

async def show_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/whitelist')
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Hanya pemilik bot yang dapat melihat daftar whitelist.")
        return
    
    users = user_manager.get_all_users()
    whitelist_info = "Daftar Whitelist Pengguna:\n"
    for user_id, data in users.items():
        limit = data.get("access_limit", "Tidak ada batas")
        whitelist_info += f"User ID: {user_id}, Batas Akses: {limit}\n"
    
    await update.message.reply_text(whitelist_info)

async def add_to_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/add')
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Hanya pemilik bot yang dapat menambahkan pengguna ke whitelist.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Penggunaan: /add <user_id>")
        return

    user_id = int(context.args[0])
    if not user_manager.is_whitelisted(user_id):
        user_manager.add_user(user_id)
        await update.message.reply_text(f"User ID {user_id} telah ditambahkan ke whitelist.")
    else:
        await update.message.reply_text("User ID sudah ada di whitelist.")

async def remove_from_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/remove')
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Hanya pemilik bot yang dapat menghapus pengguna dari whitelist.")
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Penggunaan: /remove <user_id>")
        return

    user_id = int(context.args[0])
    if user_manager.remove_user(user_id):
        await update.message.reply_text(f"User ID {user_id} telah dihapus dari whitelist.")
    else:
        await update.message.reply_text("User ID tidak ada di whitelist.")

async def set_access_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/setlimit')
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Hanya pemilik bot yang dapat mengatur batas akses.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Penggunaan: /setlimit <user_id> <limit>")
        return
    
    user_id = int(context.args[0])
    limit = int(context.args[1])
    user_manager.set_access_limit(user_id, limit)
    await update.message.reply_text(f"Batas akses untuk user ID {user_id} telah diatur menjadi {limit}.")

# File conversion functions
def txt_to_vcf(input_file, output_dir, custom_name_func, split_size, custom_filename, sequence_start=1):
    try:
        with open(input_file, 'r', encoding='utf-8') as txt_file:
            lines = [line.strip() for line in txt_file if line.strip()]

        os.makedirs(output_dir, exist_ok=True)
        vcf_data = []
        file_index = sequence_start

        for index, line in enumerate(lines, start=1):
            try:
                name, phone = (line.split(',') + [None])[:2]
                phone = phone.strip() if phone else name.strip()
                if not phone.startswith('+'):
                    phone = f"+{phone}"

                # Use the custom name pattern and add sequence number
                formatted_name = f"{custom_name_func(index)} {index}"
                vcf_data.append(f"""BEGIN:VCARD
VERSION:3.0
FN:{formatted_name}
TEL;TYPE=CELL:{phone}
END:VCARD

""")

                if split_size and len(vcf_data) == split_size:
                    output_file = os.path.join(output_dir, f"{custom_filename}{file_index}.vcf")
                    with open(output_file, 'w', encoding='utf-8') as vcf_file:
                        vcf_file.write(''.join(vcf_data))
                    file_index += 1
                    vcf_data = []
            except ValueError as e:
                print(f"Baris tidak valid, dilewati: {e}")

        if vcf_data:
            if split_size:
                output_file = os.path.join(output_dir, f"{custom_filename}{file_index}.vcf")
            else:
                output_file = os.path.join(output_dir, f"{custom_filename}.vcf")
            with open(output_file, 'w', encoding='utf-8') as vcf_file:
                vcf_file.write(''.join(vcf_data))

        # Return list of created files
        if split_size:
            return [os.path.join(output_dir, f"{custom_filename}{i}.vcf") 
                    for i in range(sequence_start, file_index + (1 if vcf_data else 0))]
        else:
            return [output_file]
    except Exception as e:
        raise Exception(f"Error in txt_to_vcf: {str(e)}")

def excel_to_vcf(input_file, output_dir, custom_name_func, split_size, custom_filename, sequence_start=1):
    try:
        df = pd.read_excel(input_file)
        os.makedirs(output_dir, exist_ok=True)
        vcf_data, file_index = [], sequence_start

        for index, row in df.iterrows():
            try:
                # Get name and phone from DataFrame
                name = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else None
                phone = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else name

                # Skip if name or phone is NaN
                if name is None or phone is None:
                    print(f"Row {index} has NaN values, skipping.")
                    continue

                if not phone.startswith('+'):
                    phone = f"+{phone}"

                # Use the custom name pattern and add sequence number
                current_index = index + 1  # Excel is 0-based, add 1 for consistency
                formatted_name = f"{custom_name_func(current_index)} {current_index}"
                vcf_data.append(f"""BEGIN:VCARD
VERSION:3.0
FN:{formatted_name}
TEL;TYPE=CELL:{phone}
END:VCARD

""")

                if split_size and len(vcf_data) == split_size:
                    output_file = os.path.join(output_dir, f"{custom_filename}{file_index}.vcf")
                    with open(output_file, 'w', encoding='utf-8') as vcf_file:
                        vcf_file.write(''.join(vcf_data))
                    file_index += 1
                    vcf_data = []
            except Exception as e:
                print(f"Baris tidak valid, dilewati: {e}")

        if vcf_data:
            if split_size:
                output_file = os.path.join(output_dir, f"{custom_filename}{file_index}.vcf")
            else:
                output_file = os.path.join(output_dir, f"{custom_filename}.vcf")
            with open(output_file, 'w', encoding='utf-8') as vcf_file:
                vcf_file.write(''.join(vcf_data))

        # Return list of created files
        if split_size:
            return [os.path.join(output_dir, f"{custom_filename}{i}.vcf") 
                    for i in range(sequence_start, file_index + (1 if vcf_data else 0))]
        else:
            return [output_file]
    except Exception as e:
        raise Exception(f"Error in excel_to_vcf: {str(e)}")

# File handlers
async def txt_to_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/txt_to_vcf')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text("Silakan unggah file .txt untuk dikonversi ke .vcf.")

async def excel_to_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, '/excel_to_vcf')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text("Silakan unggah file .xlsx untuk dikonversi ke .vcf.")

async def handle_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded TXT files."""
    try:
        await log_interaction(update, 'handle_txt_file')
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return ConversationHandler.END
        
        file_path, success = await safe_file_download(update, context, "TXT")
        if not success:
            return ConversationHandler.END
        
        context.user_data['input_file'] = file_path
        await update.message.reply_text(
            "Masukkan pola Nama kontak"
        )
        return ASK_PATTERN
    except Exception as e:
        await notify_owner_error(context, f"Error in handle_txt_file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(
            ERROR_MESSAGES["processing_error"]
        )
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def handle_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded Excel files."""
    try:
        await log_interaction(update, 'handle_excel_file')
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return ConversationHandler.END
        
        file_path, success = await safe_file_download(update, context, "Excel")
        if not success:
            return ConversationHandler.END
        
        context.user_data['input_file'] = file_path
        await update.message.reply_text(
            "Masukkan pola Nama kontak"
        )
        return ASK_PATTERN
    except Exception as e:
        await notify_owner_error(context, f"Error in handle_excel_file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(ERROR_MESSAGES["processing_error"])
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def ask_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, 'ask_split')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    context.user_data['custom_name_pattern'] = update.message.text
    keyboard = [
        [
            InlineKeyboardButton("Ya, Split File", callback_data='split'),
            InlineKeyboardButton("Tidak Perlu Split", callback_data='no_split')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Apakah Anda ingin membagi kontak menjadi beberapa file?",
        reply_markup=reply_markup
    )
    return ASK_SPLIT

async def handle_split_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, 'handle_split_choice')
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    if choice == 'split':
        await query.message.edit_text("Berapa jumlah kontak per file (masukkan angka)?")
        return ASK_SPLIT_SIZE
    else:
        context.user_data['split_size'] = None
        keyboard = [
            [
                InlineKeyboardButton("Ya", callback_data='customize_sequence'),
                InlineKeyboardButton("Tidak", callback_data='default_sequence')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "Apakah Anda ingin mengkustomisasi nomor urut file?",
            reply_markup=reply_markup
        )
        return ASK_SEQUENCE

async def ask_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await log_interaction(update, 'ask_filename')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return
    
    try:
        context.user_data['split_size'] = int(update.message.text)
        keyboard = [
            [
                InlineKeyboardButton("Ya", callback_data='customize_sequence'),
                InlineKeyboardButton("Tidak", callback_data='default_sequence')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Apakah Anda ingin mengkustomisasi nomor urut file?",
            reply_markup=reply_markup
        )
        return ASK_SEQUENCE
    except ValueError:
        await update.message.reply_text("Masukkan angka yang valid untuk jumlah kontak per file.")
        return ASK_SPLIT_SIZE

async def handle_sequence_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    if choice == 'customize_sequence':
        await query.message.edit_text("Masukkan nomor urut awal file:")
        return ASK_SEQUENCE
    else:
        context.user_data['sequence_start'] = 1
        await query.message.edit_text("Masukkan nama file output (tanpa ekstensi):")
        return ASK_FILENAME

async def handle_sequence_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sequence_start = int(update.message.text)
        context.user_data['sequence_start'] = sequence_start
        await update.message.reply_text("Masukkan nama file output (tanpa ekstensi):")
        return ASK_FILENAME
    except ValueError:
        await update.message.reply_text("Masukkan angka yang valid untuk nomor urut.")
        return ASK_SEQUENCE

async def generate_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await log_interaction(update, 'generate_vcf')
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return

        custom_filename = update.message.text.strip()
        if not custom_filename:
            await update.message.reply_text(ERROR_MESSAGES["empty_filename"])
            return ASK_FILENAME

        input_file = context.user_data['input_file']
        custom_name_pattern = context.user_data['custom_name_pattern']
        split_size = context.user_data.get('split_size')
        sequence_start = context.user_data.get('sequence_start', 1)

        success = await process_file_conversion(
            update, context, input_file, custom_name_pattern, 
            split_size, custom_filename, sequence_start
        )
        if not success:
            return ConversationHandler.END

        return ConversationHandler.END

    except Exception as e:
        error_msg = f"Error in generate_vcf: {str(e)}"
        await notify_owner_error(context, error_msg, update.effective_user.id)
        await update.message.reply_text(ERROR_MESSAGES["processing_error"])
        return ConversationHandler.END

async def notify_owner_error(context: ContextTypes.DEFAULT_TYPE, error_msg: str, user_id: int = None):
    """Notify owner about errors with structured message"""
    error_text = f"⚠️ Bot Error:\n{error_msg}\n"
    if user_id:
        error_text += f"User ID: {user_id}"
    await context.bot.send_message(chat_id=OWNER_ID, text=error_text)

async def safe_file_download(update: Update, context: ContextTypes.DEFAULT_TYPE, file_type: str) -> tuple[str, bool]:
    """
    Safely download file with proper error handling and chunked download
    Returns: (file_path, success)
    """
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    
    try:
        # Validate file size
        file_size = update.message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                ERROR_MESSAGES["file_too_large"].format(MAX_FILE_SIZE // (1024*1024))
            )
            return None, False

        # Download file
        file = await update.message.document.get_file()
        file_path = os.path.join(INPUT_DIR, update.message.document.file_name)
        temp_path = f"{file_path}.temp"
        
        status_msg = await update.message.reply_text("Mengunduh file... 0%")
        
        for attempt in range(MAX_RETRIES):
            try:
                downloaded_size = 0
                last_progress = 0
                
                async with async_timeout.timeout(MAX_DOWNLOAD_TIMEOUT):
                    # Download in chunks to temp file
                    async with aiohttp.ClientSession() as session:
                        async with session.get(file.file_path) as response:
                            with open(temp_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                                    if chunk:
                                        f.write(chunk)
                                        downloaded_size += len(chunk)
                                        progress = int((downloaded_size / file_size) * 100)
                                        
                                        # Update progress every 10%
                                        if progress - last_progress >= 10:
                                            await status_msg.edit_text(f"Mengunduh file... {progress}%")
                                            last_progress = progress
                
                # Rename temp file to final file
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rename(temp_path, file_path)
                
                await status_msg.edit_text("File berhasil diunduh!")
                return file_path, True
                
            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES - 1:
                    await status_msg.edit_text(f"Download timeout, mencoba kembali... (Percobaan {attempt + 2}/{MAX_RETRIES})")
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    await status_msg.edit_text(ERROR_MESSAGES["download_timeout"])
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    return None, False
                    
            except Exception as e:
                if "httpx.ReadError" in str(e) or isinstance(e, aiohttp.ClientError):
                    if attempt < MAX_RETRIES - 1:
                        await status_msg.edit_text(f"Koneksi terputus, mencoba kembali... (Percobaan {attempt + 2}/{MAX_RETRIES})")
                        await asyncio.sleep(RETRY_DELAY)
                    else:
                        await status_msg.edit_text("Gagal mengunduh file karena masalah koneksi. Silakan coba lagi.")
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        return None, False
                else:
                    raise

    except Exception as e:
        await notify_owner_error(context, f"Error downloading {file_type} file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(ERROR_MESSAGES["processing_error"])
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None, False

async def process_file_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE, input_file: str, 
                                custom_name_pattern: str, split_size: int, custom_filename: str,
                                sequence_start: int = 1) -> bool:
    """Process file conversion with proper error handling and progress tracking"""
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    
    try:
        status_msg = await update.message.reply_text("Sedang memproses file...")

        # Process files in a separate thread
        def convert_file():
            if input_file.lower().endswith('.txt'):
                return txt_to_vcf(input_file, OUTPUT_DIR, lambda i: custom_name_pattern.replace("{index}", str(i)),
                                split_size, custom_filename, sequence_start)
            elif input_file.lower().endswith(('.xlsx', '.xls')):
                return excel_to_vcf(input_file, OUTPUT_DIR, lambda i: custom_name_pattern.replace("{index}", str(i)),
                                  split_size, custom_filename, sequence_start)
            else:
                raise ValueError("Format file tidak didukung")

        # Run conversion in thread pool
        with ThreadPoolExecutor() as pool:
            result_files = await asyncio.get_event_loop().run_in_executor(pool, convert_file)

        total_files = len(result_files)
        await status_msg.edit_text(f"File telah diproses, sedang mengirim (0/{total_files})...")
        
        successful_sends = 0
        failed_files = []
        
        for i, file_path in enumerate(result_files, 1):
            for attempt in range(MAX_RETRIES):
                try:
                    with open(file_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=update.message.chat_id,
                            document=f,
                            filename=os.path.basename(file_path),
                            read_timeout=60,
                            write_timeout=60,
                            connect_timeout=30
                        )
                        successful_sends += 1
                        await status_msg.edit_text(f"Mengirim file ({successful_sends}/{total_files})...")
                        break  # Success, break retry loop
                        
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
                        continue
                    else:
                        failed_files.append(os.path.basename(file_path))
                        await notify_owner_error(context, f"Error sending file {file_path}: {str(e)}", update.effective_user.id)

        # Report results
        if successful_sends == total_files:
            final_message = "Konversi selesai! Semua file berhasil dikirim."
        else:
            failed_count = len(failed_files)
            final_message = f"Konversi selesai! {successful_sends}/{total_files} file berhasil dikirim."
            if failed_count > 0:
                final_message += f"\n{failed_count} file gagal dikirim: {', '.join(failed_files)}"
                final_message += "\nSilakan coba konversi ulang untuk file yang gagal."

        # Cleanup
        try:
            # Clean up input files
            if os.path.exists(input_file):
                os.remove(input_file)
            # Clean up output files
            for file_path in result_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            await notify_owner_error(context, f"Error during cleanup: {str(e)}", update.effective_user.id)

        # Update access limit only if at least one file was sent successfully
        if successful_sends > 0:
            user_manager.decrement_access_limit(update.effective_user.id)
        
        await status_msg.edit_text(final_message)
        return successful_sends > 0

    except Exception as e:
        await notify_owner_error(context, f"Error in file conversion: {str(e)}", update.effective_user.id)
        await update.message.reply_text(ERROR_MESSAGES["processing_error"])
        return False

# Merge functions
def merge_txt_files(file1_path, file2_path, output_dir, custom_filename="merged"):
    """Merge two text files with optimization."""
    try:
        # Read both files efficiently
        with open(file1_path, 'r', encoding='utf-8') as f1, \
             open(file2_path, 'r', encoding='utf-8') as f2:
            lines1 = f1.read().splitlines()
            lines2 = f2.read().splitlines()

        # Combine lines
        merged_lines = lines1 + lines2

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Write to a single output file
        output_file = os.path.join(output_dir, f"{custom_filename}.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(merged_lines))
        
        return [output_file]

    except Exception as e:
        raise Exception(f"Error in merge_txt_files: {str(e)}")

async def merge_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /merge_vcf command to start merging VCF files."""
    await log_interaction(update, '/merge_vcf')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Proses penggabungan file VCF dimulai:\n\n"
        "1. Kirim file VCF pertama\n"
        "2. Kirim file VCF kedua\n"
        "3. Kirim file VCF tambahan jika ada\n"
        "4. Ketik /done ketika semua file telah diunggah\n"
        "5. Masukkan nama file output yang diinginkan"
    )
    context.user_data['vcf_files'] = []
    return UPLOAD_VCF_FILES

async def handle_vcf_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle each VCF file upload."""
    await log_interaction(update, 'handle_vcf_file')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return ConversationHandler.END

    # Validate file type
    if not update.message.document.file_name.lower().endswith('.vcf'):
        await update.message.reply_text("Format file tidak valid. Harap kirim file dengan format .vcf")
        return UPLOAD_VCF_FILES

    # Download file
    file = await update.message.document.get_file()
    os.makedirs("input_files", exist_ok=True)
    file_path = f"input_files/{update.message.document.file_name}"
    
    status_msg = await update.message.reply_text("Mengunduh file...")
    
    try:
        # Download file
        await file.download_to_drive(file_path)
        
        # Store file path
        context.user_data['vcf_files'].append(file_path)
        await status_msg.edit_text("File VCF berhasil diunggah. Kirim file berikutnya atau ketik /done jika selesai.")
        return UPLOAD_VCF_FILES

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.edit_text("Gagal mengunduh file. Silakan coba lagi.")
        await notify_owner_error(context, f"Error downloading file: {str(e)}", update.effective_user.id)
        return UPLOAD_VCF_FILES

async def finish_vcf_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish uploading VCF files and ask for output file name."""
    await log_interaction(update, '/done')
    if not context.user_data.get('vcf_files'):
        await update.message.reply_text("Anda belum mengunggah file VCF apapun.")
        return UPLOAD_VCF_FILES

    await update.message.reply_text("Masukkan nama file output untuk file VCF yang digabungkan (tanpa ekstensi):")
    return ASK_VCF_FILENAME

async def merge_vcf_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Merge uploaded VCF files into one with a custom name."""
    await log_interaction(update, 'merge_vcf_files')
    custom_filename = update.message.text.strip()
    if not custom_filename:
        await update.message.reply_text(ERROR_MESSAGES["empty_filename"])
        return ASK_VCF_FILENAME

    vcf_files = context.user_data.get('vcf_files', [])
    output_file_path = f"output_vcf/{custom_filename}.vcf"
    os.makedirs("output_vcf", exist_ok=True)

    # Merge VCF files
    with open(output_file_path, 'w') as outfile:
        for file_path in vcf_files:
            with open(file_path, 'r') as infile:
                outfile.write(infile.read())
                outfile.write('\n')  # Ensure new line between files

    await update.message.reply_text(f"File VCF berhasil digabungkan dengan nama {custom_filename}.vcf")
    with open(output_file_path, 'rb') as f:
        await context.bot.send_document(
            chat_id=update.message.chat_id,
            document=f,
            filename=os.path.basename(output_file_path),
            read_timeout=30,
            write_timeout=30
        )

    # Cleanup
    for file_path in vcf_files:
        os.remove(file_path)
    os.remove(output_file_path)

    return ConversationHandler.END

async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /view_logs command to view user interaction logs."""
    await log_interaction(update, '/view_logs')
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You are not authorized to view the logs.")
        return

    with open(LOG_FILE, 'r') as file:
        logs = file.read()

    await update.message.reply_text(f"Logs:\n{logs}")

async def broadcast_startup(application):
    """Broadcast startup message to all whitelisted users"""
    users = user_manager.get_all_users()
    
    startup_message = (
        " Bot telah aktif dan siap digunakan!\n\n"
        "Fitur yang tersedia:\n"
        "- /start - Melihat menu utama\n"
        "- /txt_to_vcf - Konversi file .txt ke .vcf\n"
        "- /excel_to_vcf - Konversi file .xlsx ke .vcf\n"
        "- /merge_vcf - Gabungkan file .vcf\n"
        "- /create_txt - Buat file txt dari pesan\n"
        "- /checklimit - Cek sisa limit Anda\n\n"
        "Jika ada pertanyaan, silakan hubungi admin @{}"
    ).format(OWNER_USERNAME)
    
    for user_id in users:
        try:
            await application.bot.send_message(chat_id=int(user_id), text=startup_message)
        except Exception as e:
            print(f"Failed to send startup message to user {user_id}: {str(e)}")

async def broadcast_bot_dead(application):
    """Broadcast a message to all whitelisted users that the bot is dead"""
    users = user_manager.get_all_users()
    dead_message = (
        " Bot saat ini tidak aktif dan tidak dapat digunakan."
        "\nSilakan coba lagi nanti atau hubungi admin @{} jika Anda memerlukan bantuan."
    ).format(OWNER_USERNAME)
    
    for user_id in users:
        try:
            await application.bot.send_message(chat_id=int(user_id), text=dead_message)
        except Exception as e:
            print(f"Failed to send dead message to user {user_id}: {str(e)}")

async def post_init(application):
    """Post initialization hook to send startup broadcast"""
    await broadcast_startup(application)

async def clean_junk_files_and_logs():
    """Clean up junk files and logs."""
    junk_files = ["/path/to/junk1", "/path/to/junk2"]  # Example paths
    for file_path in junk_files:
        try:
            os.remove(file_path)
            print(f"Removed junk file: {file_path}")
        except Exception as e:
            print(f"Failed to remove {file_path}: {str(e)}")

async def restart_bot():
    """Restart the bot."""
    print("Restarting bot...")
    os.execv(__file__, sys.argv)  # Restart the script

async def broadcast_message(application, message):
    """Broadcast a custom message to all whitelisted users."""
    users = user_manager.get_all_users()
    for user_id in users:
        try:
            await application.bot.send_message(chat_id=int(user_id), text=message)
        except TelegramError as e:
            # Log the error and continue with the next user
            print(f"Skipping user {user_id}: {str(e)}")
            continue
        except Exception as e:
            # Log any other exceptions and continue
            print(f"Failed to send message to user {user_id}: {str(e)}")
            continue

# Example usage of broadcast_message
# await broadcast_message(application, "This is a broadcast message from the owner.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allow the owner to broadcast a message to all users via a command."""
    user_id = update.effective_user.id
    if user_manager.is_owner(user_id):
        if context.args:
            message = ' '.join(context.args)
            await broadcast_message(context.application, message)
            await update.message.reply_text("Broadcast message sent.")
        else:
            await update.message.reply_text("Please provide a message to broadcast.")
    else:
        await update.message.reply_text("You are not authorized to perform this action.")

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restart the bot via a Telegram command."""
    user_id = update.effective_user.id
    if user_manager.is_owner(user_id):  # Assuming a function to check if the user is the owner
        await update.message.reply_text("Restarting bot...")
        restart_bot()
    else:
        await update.message.reply_text("You are not authorized to perform this action.")

class RestartOnChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print(f"Detected change in {event.src_path}. Restarting bot...")
            restart_bot()

async def create_txt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /create_txt command"""
    await log_interaction(update, '/create_txt')
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return ConversationHandler.END
    
    await update.message.reply_text("Silakan kirim pesan yang ingin Anda jadikan file txt:")
    return CREATE_TXT_MESSAGE

async def handle_txt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message content for txt creation"""
    await log_interaction(update, 'handle_txt_message')
    message = update.message.text
    context.user_data['txt_content'] = message
    
    await update.message.reply_text("Masukkan nama file untuk menyimpan pesan Anda (tanpa ekstensi .txt):")
    return CREATE_TXT_FILENAME

async def save_txt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the message as a txt file"""
    await log_interaction(update, 'save_txt_message')
    filename = update.message.text.strip()
    if not filename:
        await update.message.reply_text(ERROR_MESSAGES["empty_filename"])
        return CREATE_TXT_FILENAME
    
    # Add .txt extension if not present
    if not filename.endswith('.txt'):
        filename = f"{filename}.txt"
    
    file_path = os.path.join(OUTPUT_DIR, filename)
    temp_msg = None
    
    try:
        # Send a temporary message to show progress
        temp_msg = await update.message.reply_text("Sedang membuat file txt...")
        
        # Write content to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(context.user_data['txt_content'])
        
        # Reduce user's access limit
        user_id = update.effective_user.id
        user_manager.decrement_access_limit(user_id)
        current_limit = user_manager.get_access_limit(user_id)
        
        # Send the file using chunks to prevent timeout
        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"File txt berhasil dibuat! Sisa limit Anda: {current_limit}",
                    read_timeout=30,
                    write_timeout=30
                )
        except Exception as e:
            await update.message.reply_text(
                "Gagal mengirim file. Silakan coba lagi dengan pesan yang lebih pendek."
            )
            raise e
            
    except Exception as e:
        error_msg = f"Terjadi kesalahan saat membuat file txt: {str(e)}"
        await update.message.reply_text(error_msg)
        await notify_owner_error(context, str(e), update.effective_user.id)
        
    finally:
        # Clean up
        if temp_msg:
            try:
                await temp_msg.delete()
            except:
                pass
                
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        # Clear user data
        if 'txt_content' in context.user_data:
            del context.user_data['txt_content']
    
    return ConversationHandler.END

if __name__ == "__main__":
    def main():
        """Start the bot."""
        # Create the Application
        application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
        
        # Add error handler
        application.add_error_handler(error_handler)

        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("txt_to_vcf", txt_to_vcf_handler),
                CommandHandler("excel_to_vcf", excel_to_vcf_handler),
                MessageHandler(filters.Document.FileExtension("txt"), handle_txt_file),
                MessageHandler(filters.Document.FileExtension("xlsx"), handle_excel_file),
            ],
            states={
                ASK_PATTERN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_split)],
                ASK_SPLIT: [CallbackQueryHandler(handle_split_choice)],
                ASK_SPLIT_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_filename)],
                ASK_SEQUENCE: [
                    CallbackQueryHandler(handle_sequence_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sequence_number)
                ],
                ASK_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_vcf)]
            },
            fallbacks=[],
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("getid", get_id))
        application.add_handler(CommandHandler("checklimit", checklimit))
        application.add_handler(CommandHandler("add", add_to_whitelist))
        application.add_handler(CommandHandler("remove", remove_from_whitelist))
        application.add_handler(CommandHandler("setlimit", set_access_limit))
        application.add_handler(CommandHandler("whitelist", show_whitelist))
        application.add_handler(conv_handler)

        create_txt_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("create_txt", create_txt_handler)],
            states={
                CREATE_TXT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txt_message)],
                CREATE_TXT_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_txt_message)]
            },
            fallbacks=[],
        )
        application.add_handler(create_txt_conv_handler)

        merge_vcf_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("merge_vcf", merge_vcf_handler)],
            states={
                UPLOAD_VCF_FILES: [
                    MessageHandler(filters.Document.FileExtension("vcf") & filters.ChatType.PRIVATE, handle_vcf_file),
                    CommandHandler("done", finish_vcf_upload)
                ],
                ASK_VCF_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, merge_vcf_files)]
            },
            fallbacks=[],
        )
        application.add_handler(merge_vcf_conv_handler)

        application.add_handler(CommandHandler("view_logs", view_logs))
        application.add_handler(CommandHandler("restart", restart_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))

        print("Bot berjalan...")
        
        # Setup file watcher
        observer = Observer()
        observer.schedule(RestartOnChangeHandler(), path='.', recursive=True)
        observer.start()

        try:
            # Start the bot
            application.run_polling(drop_pending_updates=True)
        finally:
            observer.stop()
            observer.join()

    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors in the bot."""
        error = context.error
        try:
            if update:
                user_id = update.effective_user.id if update.effective_user else "Unknown"
            else:
                user_id = "Unknown"
            
            error_msg = f"An error occurred:\nError: {str(error)}\nUser ID: {user_id}"
            await notify_owner_error(context, error_msg, user_id if isinstance(user_id, int) else None)
            
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "Sorry, an error occurred while processing your request. The bot owner has been notified."
                )
        except Exception as e:
            print(f"Error in error handler: {str(e)}")

    main()