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

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))

# Initialize user manager
user_manager = UserManager()

# State for ConversationHandler
ASK_PATTERN, ASK_SPLIT, ASK_SPLIT_SIZE, ASK_FILENAME = range(4)

# Access denied message
ACCESS_DENIED_MESSAGE = "Anda tidak memiliki akses ke bot ini. Hubungi admin untuk mendapatkan akses bot"

# Constants
MAX_DOWNLOAD_TIMEOUT = 300  # 5 minutes timeout for downloads
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size

def check_whitelist(user_id: int) -> bool:
    """Check if user_id is in whitelist."""
    return user_manager.is_whitelisted(user_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ACCESS_DENIED_MESSAGE)
        return

    await update.message.reply_text(
        "Halo! Pilih fitur yang ingin Anda gunakan:\n"
        "- /txt_to_vcf: Konversi file .txt ke .vcf\n"
        "- /excel_to_vcf: Konversi file .xlsx ke .vcf\n"
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
                    output_file = os.path.join(output_dir, f"{custom_filename}_{file_index}.vcf")
                    with open(output_file, 'w', encoding='utf-8') as vcf_file:
                        vcf_file.write(''.join(vcf_data))
                    file_index += 1
                    vcf_data = []
            except ValueError as e:
                print(f"Baris tidak valid, dilewati: {e}")

        if vcf_data:
            output_file = os.path.join(output_dir, f"{custom_filename}_{file_index}.vcf")
            with open(output_file, 'w', encoding='utf-8') as vcf_file:
                vcf_file.write(''.join(vcf_data))
            
        # Return list of created files
        return [os.path.join(output_dir, f"{custom_filename}_{i}.vcf") 
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
                    output_file = os.path.join(output_dir, f"{custom_filename}_{file_index}.vcf")
                    with open(output_file, 'w', encoding='utf-8') as vcf_file:
                        vcf_file.write(''.join(vcf_data))
                    file_index += 1
                    vcf_data = []
            except Exception as e:
                print(f"Baris tidak valid, dilewati: {e}")

        if vcf_data:
            output_file = os.path.join(output_dir, f"{custom_filename}_{file_index}.vcf")
            with open(output_file, 'w', encoding='utf-8') as vcf_file:
                vcf_file.write(''.join(vcf_data))

        # Return list of created files
        return [os.path.join(output_dir, f"{custom_filename}_{i}.vcf") 
                for i in range(1, file_index + (1 if vcf_data else 0))]
    except Exception as e:
        raise Exception(f"Error in excel_to_vcf: {str(e)}")

# File handlers
async def txt_to_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ACCESS_DENIED_MESSAGE)
        return

    await update.message.reply_text("Silakan unggah file .txt untuk dikonversi ke .vcf.")

async def excel_to_vcf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ACCESS_DENIED_MESSAGE)
        return

    await update.message.reply_text("Silakan unggah file .xlsx untuk dikonversi ke .vcf.")

async def handle_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded TXT files."""
    try:
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ACCESS_DENIED_MESSAGE)
            return

        # Check file size
        file_size = update.message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f"File terlalu besar. Maksimal ukuran file adalah {MAX_FILE_SIZE // (1024*1024)}MB."
            )
            return ConversationHandler.END

        # Get file
        file = await update.message.document.get_file()
        os.makedirs("input_files", exist_ok=True)
        file_path = f"input_files/{update.message.document.file_name}"
        
        # Send status message
        status_msg = await update.message.reply_text("Mengunduh file...")
        
        try:
            async with async_timeout.timeout(MAX_DOWNLOAD_TIMEOUT):
                await file.download_to_drive(file_path)
                await status_msg.edit_text("File berhasil diunduh!")
        except asyncio.TimeoutError:
            await status_msg.edit_text("Waktu unduh habis. Silakan coba lagi dengan file yang lebih kecil.")
            if os.path.exists(file_path):
                os.remove(file_path)
            return ConversationHandler.END
        
        context.user_data['input_file'] = file_path
        await update.message.reply_text(
            "Masukkan pola Nama kontak"
        )
        return ASK_PATTERN
    except Exception as e:
        await notify_owner_error(context, f"Error in handle_txt_file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(
            "Maaf, terjadi kesalahan saat memproses file. Admin telah diberitahu."
        )
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def handle_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded Excel files."""
    try:
        if not check_whitelist(update.effective_user.id):
            await update.message.reply_text(ACCESS_DENIED_MESSAGE)
            return

        # Check file size
        file_size = update.message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await update.message.reply_text(
                f"File terlalu besar. Maksimal ukuran file adalah {MAX_FILE_SIZE // (1024*1024)}MB."
            )
            return ConversationHandler.END

        # Get file
        file = await update.message.document.get_file()
        os.makedirs("input_files", exist_ok=True)
        file_path = f"input_files/{update.message.document.file_name}"
        
        # Send status message
        status_msg = await update.message.reply_text("Mengunduh file...")
        
        try:
            async with async_timeout.timeout(MAX_DOWNLOAD_TIMEOUT):
                await file.download_to_drive(file_path)
                await status_msg.edit_text("File berhasil diunduh!")
        except asyncio.TimeoutError:
            await status_msg.edit_text("Waktu unduh habis. Silakan coba lagi dengan file yang lebih kecil.")
            if os.path.exists(file_path):
                os.remove(file_path)
            return ConversationHandler.END
        
        context.user_data['input_file'] = file_path
        await update.message.reply_text(
            "Masukkan pola Nama kontak"
        )
        return ASK_PATTERN
    except Exception as e:
        await notify_owner_error(context, f"Error in handle_excel_file: {str(e)}", update.effective_user.id)
        await update.message.reply_text(
            "Maaf, terjadi kesalahan saat memproses file. Admin telah diberitahu."
        )
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return ConversationHandler.END

async def ask_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_whitelist(update.effective_user.id):
        await update.message.reply_text(ACCESS_DENIED_MESSAGE)
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
        await update.message.reply_text(ACCESS_DENIED_MESSAGE)
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
            await update.message.reply_text(ACCESS_DENIED_MESSAGE)
            return

        custom_filename = update.message.text
        input_file = context.user_data['input_file']
        custom_name_pattern = context.user_data['custom_name_pattern']
        split_size = context.user_data.get('split_size')
        output_dir = "output_vcf"

        custom_name_func = lambda index: custom_name_pattern.replace("{index}", str(index))
        os.makedirs(output_dir, exist_ok=True)

        status_msg = await update.message.reply_text("Sedang memproses file...")

        # Process files in a separate thread to prevent timeout
        def process_file():
            if input_file.lower().endswith('.txt'):
                return txt_to_vcf(input_file, output_dir, custom_name_func, split_size, custom_filename)
            elif input_file.lower().endswith(('.xlsx', '.xls')):
                return excel_to_vcf(input_file, output_dir, custom_name_func, split_size, custom_filename)
            else:
                raise ValueError("Format file tidak didukung")

        # Run file processing in thread pool
        with ThreadPoolExecutor() as pool:
            files = await asyncio.get_event_loop().run_in_executor(pool, process_file)

        # Update status message
        await status_msg.edit_text("File telah diproses, sedang mengirim...")

        # Send files in chunks to prevent timeout
        chunk_size = 5
        for i in range(0, len(files), chunk_size):
            chunk = files[i:i + chunk_size]
            for file in chunk:
                try:
                    with open(file, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=update.message.chat_id,
                            document=f,
                            read_timeout=30,
                            write_timeout=30
                        )
                except Exception as e:
                    await notify_owner_error(context, f"Error sending file {file}: {str(e)}", update.effective_user.id)
                    continue

            # Update progress after each chunk
            files_sent = min(i + chunk_size, len(files))
            await status_msg.edit_text(f"Mengirim file... ({files_sent}/{len(files)})")

        # Cleanup
        try:
            os.remove(input_file)
            for file in files:
                if os.path.exists(file):
                    os.remove(file)
        except Exception as e:
            await notify_owner_error(context, f"Error during cleanup: {str(e)}", update.effective_user.id)

        # Update access limit after successful conversion
        user_id = update.effective_user.id
        user_manager.decrement_access_limit(user_id)

        await status_msg.edit_text("Konversi selesai!")
        return ConversationHandler.END

    except Exception as e:
        error_msg = f"Error in generate_vcf: {str(e)}"
        await notify_owner_error(context, error_msg, update.effective_user.id)
        await update.message.reply_text(
            "Maaf, terjadi kesalahan saat mengkonversi file. Admin telah diberitahu."
        )
        return ConversationHandler.END

async def notify_owner_error(context: ContextTypes.DEFAULT_TYPE, error_msg: str, user_id: int = None):
    """Send error notification to owner."""
    user_info = f" (User ID: {user_id})" if user_id else ""
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=f"⚠️ Bot Error{user_info}:\n{error_msg}"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors and notify owner."""
    error_msg = f"An error occurred: {context.error}"
    user_id = update.effective_user.id if update and update.effective_user else None
    await notify_owner_error(context, error_msg, user_id)
    if update:
        await update.message.reply_text(
            "Maaf, terjadi kesalahan. Admin telah diberitahu dan akan segera memperbaikinya."
        )

def main():
    """Start the bot."""
    # Create the Application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

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
            ASK_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_vcf)],
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

    print("Bot berjalan...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
