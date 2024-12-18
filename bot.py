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
from concurrent.futures import ThreadPoolExecutor
import time

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
for directory in [DOWNLOAD_DIR, OUTPUT_DIR, INPUT_DIR]:
    os.makedirs(directory, exist_ok=True)

# State for ConversationHandler
ASK_PATTERN, ASK_SPLIT, ASK_SPLIT_SIZE, ASK_FILENAME = range(4)
# States for merge conversation
UPLOAD_FIRST_FILE, UPLOAD_SECOND_FILE, ASK_MERGE_FILENAME = range(4, 7)
# States for create txt conversation
CREATE_TXT_MESSAGE, CREATE_TXT_FILENAME = range(7, 9)

def check_whitelist(user_id: int) -> bool:
    """Check if user is whitelisted and has remaining access"""
    if not user_manager.is_whitelisted(user_id):
        return False
    limit = user_manager.get_access_limit(user_id)
    return limit is not None and limit > 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text(
        "Halo! Pilih fitur yang ingin Anda gunakan:\n"
        "- /txt_to_vcf: Konversi file .txt ke .vcf\n"
        "- /excel_to_vcf: Konversi file .xlsx ke .vcf\n"
        "- /merge_txt: Gabungkan 2 file .txt\n"
        "- /create_txt: Buat file txt dari pesan\n"
        "Silakan ketik salah satu perintah untuk memulai."
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"ID Anda adalah: {user_id}")

async def check_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    limit = user_manager.get_access_limit(user_id)
    
    if limit is None:
        await update.message.reply_text("Anda tidak memiliki batas akses yang ditetapkan.")
    else:
        await update.message.reply_text(f"Batas akses Anda tersisa: {limit}")

async def show_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
def txt_to_vcf(input_file, output_dir, custom_name_func, split_size, custom_filename):
    try:
        with open(input_file, 'r', encoding='utf-8') as txt_file:
            lines = [line.strip() for line in txt_file if line.strip()]

        os.makedirs(output_dir, exist_ok=True)
        vcf_data, file_index = [], 1

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
            output_file = os.path.join(output_dir, f"{custom_filename}{file_index}.vcf")
            with open(output_file, 'w', encoding='utf-8') as vcf_file:
                vcf_file.write(''.join(vcf_data))
            
        # Return list of created files
        return [os.path.join(output_dir, f"{custom_filename}{i}.vcf") 
                for i in range(1, file_index + (1 if vcf_data else 0))]
    except Exception as e:
        raise Exception(f"Error in txt_to_vcf: {str(e)}")

def excel_to_vcf(input_file, output_dir, custom_name_func, split_size, custom_filename):
    try:
        df = pd.read_excel(input_file)
        os.makedirs(output_dir, exist_ok=True)
        vcf_data, file_index = [], 1

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
            output_file = os.path.join(output_dir, f"{custom_filename}{file_index}.vcf")
            with open(output_file, 'w', encoding='utf-8') as vcf_file:
                vcf_file.write(''.join(vcf_data))

        # Return list of created files
        return [os.path.join(output_dir, f"{custom_filename}{i}.vcf") 
                for i in range(1, file_index + (1 if vcf_data else 0))]
    except Exception as e:
        raise Exception(f"Error in excel_to_vcf: {str(e)}")

# File handlers
async def txt_to_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text("Silakan unggah file .txt untuk dikonversi ke .vcf.")

async def excel_to_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text("Silakan unggah file .xlsx untuk dikonversi ke .vcf.")

async def handle_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded TXT files."""
    try:
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return

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
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return

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
        await update.message.reply_text(
            ERROR_MESSAGES["processing_error"]
        )
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def ask_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    if choice == 'split':
        await query.message.edit_text("Berapa jumlah kontak per file (masukkan angka)?")
        return ASK_SPLIT_SIZE
    else:
        context.user_data['split_size'] = None
        await query.message.edit_text("Masukkan nama file output (tanpa ekstensi):")
        return ASK_FILENAME

async def ask_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return
    
    try:
        context.user_data['split_size'] = int(update.message.text)
        await update.message.reply_text("Masukkan nama dasar untuk file output.")
        return ASK_FILENAME
    except ValueError:
        await update.message.reply_text("Masukkan angka yang valid untuk jumlah kontak per file.")
        return ASK_SPLIT_SIZE

async def generate_vcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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

        success = await process_file_conversion(update, context, input_file, custom_name_pattern, split_size, custom_filename)
        if not success:
            return ConversationHandler.END

        return ConversationHandler.END

    except Exception as e:
        error_msg = f"Error in generate_vcf: {str(e)}"
        await notify_owner_error(context, error_msg, update.effective_user.id)
        await update.message.reply_text(
            ERROR_MESSAGES["processing_error"]
        )
        return ConversationHandler.END

async def notify_owner_error(context: ContextTypes.DEFAULT_TYPE, error_msg: str, user_id: int = None):
    """Notify owner about errors with structured message"""
    error_text = f"⚠️ Bot Error:\n{error_msg}\n"
    if user_id:
        error_text += f"User ID: {user_id}"
    await context.bot.send_message(chat_id=OWNER_ID, text=error_text)

async def safe_file_download(update: Update, context: ContextTypes.DEFAULT_TYPE, file_type: str) -> tuple[str, bool]:
    """
    Safely download file with proper error handling
    Returns: (file_path, success)
    """
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
        
        status_msg = await update.message.reply_text("Mengunduh file...")
        
        try:
            async with async_timeout.timeout(MAX_DOWNLOAD_TIMEOUT):
                await file.download_to_drive(file_path)
                await status_msg.edit_text("File berhasil diunduh!")
                return file_path, True
        except asyncio.TimeoutError:
            await status_msg.edit_text(ERROR_MESSAGES["download_timeout"])
            if os.path.exists(file_path):
                os.remove(file_path)
            return None, False

    except Exception as e:
        await notify_owner_error(context, f"Error downloading {file_type} file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(ERROR_MESSAGES["processing_error"])
        return None, False

async def process_file_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE, input_file: str, 
                                custom_name_pattern: str, split_size: int, custom_filename: str) -> bool:
    """Process file conversion with proper error handling"""
    try:
        status_msg = await update.message.reply_text("Sedang memproses file...")

        # Process files in a separate thread
        def convert_file():
            if input_file.lower().endswith('.txt'):
                return txt_to_vcf(input_file, OUTPUT_DIR, lambda i: custom_name_pattern.replace("{index}", str(i)),
                                split_size, custom_filename)
            elif input_file.lower().endswith(('.xlsx', '.xls')):
                return excel_to_vcf(input_file, OUTPUT_DIR, lambda i: custom_name_pattern.replace("{index}", str(i)),
                                  split_size, custom_filename)
            else:
                raise ValueError(ERROR_MESSAGES["unsupported_format"])

        # Run conversion in thread pool
        with ThreadPoolExecutor() as pool:
            result_files = await asyncio.get_event_loop().run_in_executor(pool, convert_file)

        # Send files
        await status_msg.edit_text("File telah diproses, sedang mengirim...")
        
        for i, file_path in enumerate(result_files, 1):
            try:
                with open(file_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.message.chat_id,
                        document=f,
                        filename=os.path.basename(file_path),
                        read_timeout=30,
                        write_timeout=30
                    )
            except Exception as e:
                await notify_owner_error(context, f"Error sending file {file_path}: {str(e)}", update.effective_user.id)
                continue

        # Cleanup
        cleanup_files([input_file] + result_files)
        
        # Update access limit
        user_manager.decrement_access_limit(update.effective_user.id)
        
        await status_msg.edit_text("Konversi selesai!")
        return True

    except Exception as e:
        await notify_owner_error(context, f"Error in file conversion: {str(e)}", update.effective_user.id)
        await update.message.reply_text(ERROR_MESSAGES["processing_error"])
        return False

def cleanup_files(files: list[str]):
    """Safely cleanup files"""
    for file in files:
        try:
            if file and os.path.exists(file):
                os.remove(file)
        except Exception:
            pass

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

async def merge_txt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /merge_txt command."""
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return

    await update.message.reply_text(
        " Proses penggabungan file TXT dimulai:\n\n"
        "1. Kirim file TXT pertama\n"
        " Anda memiliki waktu 1 menit untuk mengirim setiap file."
    )
    context.user_data['merge_mode'] = True
    context.user_data['upload_time'] = time.time()
    return UPLOAD_FIRST_FILE

async def handle_first_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle first TXT file upload for merging."""
    try:
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return ConversationHandler.END

        # Verify this is actually the first file upload
        if context.user_data.get('first_file'):
            await update.message.reply_text(
                " File pertama sudah diterima.\n"
                "Silakan kirim file kedua atau mulai ulang dengan /merge_txt"
            )
            return UPLOAD_SECOND_FILE

        # Check upload timeout
        current_time = time.time()
        last_upload_time = context.user_data.get('upload_time', 0)
        if current_time - last_upload_time > FILE_UPLOAD_TIMEOUT:
            await update.message.reply_text(
                " Waktu upload telah habis. Silakan mulai ulang dengan /merge_txt"
            )
            return ConversationHandler.END

        # Validate file type
        if not update.message.document.file_name.lower().endswith('.txt'):
            await update.message.reply_text(
                " Format file tidak valid. Harap kirim file dengan format .txt"
            )
            return UPLOAD_FIRST_FILE

        # Check file size
        file_size = update.message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f" File terlalu besar. Maksimal ukuran file adalah {MAX_FILE_SIZE // (1024*1024)}MB."
            )
            return ConversationHandler.END

        # Get file
        file = await update.message.document.get_file()
        os.makedirs("input_files", exist_ok=True)
        file_path = f"input_files/{update.message.document.file_name}"
        
        status_msg = await update.message.reply_text("Mengunduh file pertama...")
        
        try:
            async with async_timeout.timeout(MAX_DOWNLOAD_TIMEOUT):
                await file.download_to_drive(file_path)
                
                # Verify file is not empty
                if os.path.getsize(file_path) == 0:
                    await status_msg.edit_text(" File kosong. Silakan kirim file yang berisi teks.")
                    os.remove(file_path)
                    return UPLOAD_FIRST_FILE

                await status_msg.edit_text(
                    " File pertama berhasil diunduh!\n\n"
                    "Langkah selanjutnya:\n"
                    "2. Silakan kirim file TXT kedua yang akan digabungkan.\n"
                    " Anda memiliki waktu 1 menit untuk mengirim file kedua."
                )
                
                # Store file info
                context.user_data['first_file'] = file_path
                context.user_data['first_filename'] = update.message.document.file_name
                context.user_data['upload_time'] = time.time()  # Reset timer for second file
                
                return UPLOAD_SECOND_FILE

        except asyncio.TimeoutError:
            await status_msg.edit_text(" Waktu unduh habis. Silakan coba lagi dengan file yang lebih kecil.")
            if os.path.exists(file_path):
                os.remove(file_path)
            return ConversationHandler.END
        
    except Exception as e:
        await notify_owner_error(context, f"Error in handle_first_txt_file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(
            " Maaf, terjadi kesalahan saat memproses file. Admin telah diberitahu."
        )
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def handle_second_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle second TXT file upload for merging."""
    try:
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return ConversationHandler.END

        # Verify first file was uploaded
        if not context.user_data.get('first_file'):
            await update.message.reply_text(
                " File pertama belum diterima.\n"
                "Silakan mulai ulang dengan /merge_txt"
            )
            return ConversationHandler.END

        # Check upload timeout
        current_time = time.time()
        last_upload_time = context.user_data.get('upload_time', 0)
        if current_time - last_upload_time > FILE_UPLOAD_TIMEOUT:
            # Cleanup first file if it exists
            first_file = context.user_data.get('first_file')
            if first_file and os.path.exists(first_file):
                os.remove(first_file)
            await update.message.reply_text(
                " Waktu upload telah habis. Silakan mulai ulang dengan /merge_txt"
            )
            context.user_data.clear()
            return ConversationHandler.END

        # Validate file type
        if not update.message.document.file_name.lower().endswith('.txt'):
            await update.message.reply_text(
                " Format file tidak valid. Harap kirim file dengan format .txt"
            )
            return UPLOAD_SECOND_FILE

        # Check file size
        file_size = update.message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f" File terlalu besar. Maksimal ukuran file adalah {MAX_FILE_SIZE // (1024*1024)}MB."
            )
            return ConversationHandler.END

        # Get file
        file = await update.message.document.get_file()
        os.makedirs("input_files", exist_ok=True)
        file_path = f"input_files/{update.message.document.file_name}"
        
        status_msg = await update.message.reply_text("Mengunduh file kedua...")
        
        try:
            async with async_timeout.timeout(MAX_DOWNLOAD_TIMEOUT):
                await file.download_to_drive(file_path)
                
                # Verify file is not empty
                if os.path.getsize(file_path) == 0:
                    await status_msg.edit_text(" File kosong. Silakan kirim file yang berisi teks.")
                    os.remove(file_path)
                    return UPLOAD_SECOND_FILE

                await status_msg.edit_text(
                    " File kedua berhasil diunduh!\n\n"
                    "Langkah terakhir:\n"
                    "3. Masukkan nama file hasil gabungan (tanpa ekstensi)\n"
                    "Contoh: merged_file"
                )
                
                # Store file info
                context.user_data['second_file'] = file_path
                context.user_data['second_filename'] = update.message.document.file_name
                
                return ASK_MERGE_FILENAME

        except asyncio.TimeoutError:
            await status_msg.edit_text(" Waktu unduh habis. Silakan coba lagi dengan file yang lebih kecil.")
            if os.path.exists(file_path):
                os.remove(file_path)
            return ConversationHandler.END
        
    except Exception as e:
        await notify_owner_error(context, f"Error in handle_second_txt_file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(
            " Maaf, terjadi kesalahan saat memproses file. Admin telah diberitahu."
        )
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def handle_merge_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle merge filename input and process the merge."""
    try:
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
            return ConversationHandler.END

        custom_filename = update.message.text.strip()
        if not custom_filename:
            await update.message.reply_text(ERROR_MESSAGES["empty_filename"])
            return ASK_MERGE_FILENAME

        # Get files from context
        file1 = context.user_data.get('first_file')
        file2 = context.user_data.get('second_file')
        
        # Comprehensive validation of files
        if not all([file1, file2]):
            missing_files = []
            if not file1:
                missing_files.append("pertama")
            if not file2:
                missing_files.append("kedua")
            
            await update.message.reply_text(
                f"File {' dan '.join(missing_files)} belum dikirim. "
                "Silakan mulai ulang dengan /merge_txt"
            )
            # Cleanup any existing files
            for file in [file1, file2]:
                if file and os.path.exists(file):
                    os.remove(file)
            context.user_data.clear()
            return ConversationHandler.END
            
        # Validate files exist on disk and are readable
        files_status = []
        for idx, file in enumerate([file1, file2], 1):
            try:
                if not os.path.exists(file):
                    files_status.append(f"File {idx} tidak ditemukan")
                elif not os.access(file, os.R_OK):
                    files_status.append(f"File {idx} tidak dapat dibaca")
                elif os.path.getsize(file) == 0:
                    files_status.append(f"File {idx} kosong")
            except Exception:
                files_status.append(f"Error saat memeriksa file {idx}")
        
        if files_status:
            error_message = "Terjadi masalah dengan file yang dikirim:\n" + "\n".join(files_status)
            await update.message.reply_text(
                f"{error_message}\nSilakan mulai ulang dengan /merge_txt"
            )
            # Cleanup any existing files
            for file in [file1, file2]:
                if file and os.path.exists(file):
                    os.remove(file)
            context.user_data.clear()
            return ConversationHandler.END

        output_dir = "output_merged"

        status_msg = await update.message.reply_text("Sedang menggabungkan file...")

        # Process files in a separate thread
        def process_merge():
            return merge_txt_files(file1, file2, output_dir, custom_filename)

        # Run merge processing in thread pool
        with ThreadPoolExecutor() as pool:
            output_files = await asyncio.get_event_loop().run_in_executor(pool, process_merge)

        # Send files
        await status_msg.edit_text("File telah digabung, sedang mengirim...")

        for i, file_path in enumerate(output_files, 1):
            try:
                with open(file_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.message.chat_id,
                        document=f,
                        filename=os.path.basename(file_path),
                        read_timeout=30,
                        write_timeout=30
                    )
            except Exception as e:
                await notify_owner_error(context, f"Error sending merged file {file_path}: {str(e)}", update.effective_user.id)
                continue

        # Cleanup
        try:
            if os.path.exists(file1):
                os.remove(file1)
            if os.path.exists(file2):
                os.remove(file2)
            for file_path in output_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            await notify_owner_error(context, f"Error during merge cleanup: {str(e)}", update.effective_user.id)

        # Update access limit
        user_id = update.effective_user.id
        user_manager.decrement_access_limit(user_id)
        current_limit = user_manager.get_access_limit(user_id)

        # Clear user data
        context.user_data.clear()

        await status_msg.edit_text("Penggabungan file selesai!")
        return ConversationHandler.END

    except Exception as e:
        error_msg = f"Error in handle_merge_filename: {str(e)}"
        await notify_owner_error(context, error_msg, update.effective_user.id)
        await update.message.reply_text(
            " Maaf, terjadi kesalahan saat menggabungkan file. Admin telah diberitahu."
        )
        # Cleanup on error
        file1 = context.user_data.get('first_file')
        file2 = context.user_data.get('second_file')
        for file in [file1, file2]:
            if file and os.path.exists(file):
                os.remove(file)
        context.user_data.clear()
        return ConversationHandler.END

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

async def create_txt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /create_txt command"""
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ERROR_MESSAGES["access_denied"].format(OWNER_USERNAME))
        return ConversationHandler.END
    
    await update.message.reply_text("Silakan kirim pesan yang ingin Anda jadikan file txt:")
    return CREATE_TXT_MESSAGE

async def handle_txt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message content for txt creation"""
    message = update.message.text
    context.user_data['txt_content'] = message
    
    await update.message.reply_text("Masukkan nama file untuk menyimpan pesan Anda (tanpa ekstensi .txt):")
    return CREATE_TXT_FILENAME

async def save_txt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the message as a txt file"""
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
        except Exception as send_error:
            await update.message.reply_text(
                "Gagal mengirim file. Silakan coba lagi dengan pesan yang lebih pendek."
            )
            raise send_error
            
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

async def broadcast_startup(application):
    """Broadcast startup message to all whitelisted users"""
    users = user_manager.get_all_users()
    
    startup_message = (
        "🤖 Bot telah aktif dan siap digunakan!\n\n"
        "Fitur yang tersedia:\n"
        "- /start - Melihat menu utama\n"
        "- /txt_to_vcf - Konversi file .txt ke .vcf\n"
        "- /excel_to_vcf - Konversi file .xlsx ke .vcf\n"
        "- /merge_txt - Gabungkan 2 file .txt\n"
        "- /create_txt - Buat file txt dari pesan\n"
        "- /check_limit - Cek sisa limit Anda\n\n"
        "Jika ada pertanyaan, silakan hubungi admin @{}"
    ).format(OWNER_USERNAME)
    
    for user_id in users:
        try:
            await application.bot.send_message(chat_id=int(user_id), text=startup_message)
        except Exception as e:
            print(f"Failed to send startup message to user {user_id}: {str(e)}")

async def post_init(application):
    """Post initialization hook to send startup broadcast"""
    await broadcast_startup(application)

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
            CommandHandler("merge_txt", merge_txt_handler),
            MessageHandler(filters.Document.FileExtension("txt") & filters.ChatType.PRIVATE, handle_first_txt_file),
            MessageHandler(filters.Document.FileExtension("txt") & filters.ChatType.PRIVATE, handle_second_txt_file),
        ],
        states={
            ASK_PATTERN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_split)],
            ASK_SPLIT: [CallbackQueryHandler(handle_split_choice)],
            ASK_SPLIT_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_filename)],
            ASK_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_vcf)],
            UPLOAD_FIRST_FILE: [MessageHandler(filters.Document.FileExtension("txt") & filters.ChatType.PRIVATE, handle_first_txt_file)],
            UPLOAD_SECOND_FILE: [MessageHandler(filters.Document.FileExtension("txt") & filters.ChatType.PRIVATE, handle_second_txt_file)],
            ASK_MERGE_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_merge_filename)],
        },
        fallbacks=[],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("getid", get_id))
    application.add_handler(CommandHandler("checklimit", check_limit))
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

    print("Bot berjalan...")
    
    # Start the bot
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
