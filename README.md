# Telegram Contact Converter Bot

A Telegram bot that converts text and Excel files to VCF (vCard) format with robust error handling and progress tracking.

## Features

- Convert TXT files to VCF format
- Convert Excel (XLSX) files to VCF format
- User access control with whitelist
- Access limit management per user
- Customizable contact naming patterns
- Split output into multiple VCF files
- Handles NaN values in Excel files gracefully
- Improved error handling and user notifications

## Enhanced Features

- **Robust File Handling**:
  - Chunked file downloads for better performance
  - Progress tracking for downloads and uploads
  - Automatic retry on network failures
  - Temporary file handling to prevent corruption

- **Improved Error Recovery**:
  - Automatic retry for failed uploads (3 attempts)
  - Detailed error messages and progress updates
  - Better cleanup of temporary files
  - Smart access limit management

- **User Experience**:
  - Real-time progress updates
  - Download progress percentage
  - Upload counter for multiple files
  - Detailed success/failure reporting

- **Admin Features**:
  - Junk file cleaning
  - Bot restart command
  - Broadcast messaging
  - Detailed error notifications

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following content:
   ```plaintext
   BOT_TOKEN="YOUR_TOKEN"
   OWNER_ID="YOUR_ID"
   OWNER_USERNAME="YOUR_USERNAME"
   ```

4. Run the bot:
   ```bash
   python3 bot.py
   ```

## Running the Bot as a Background Service

To run the Telegram Contact Converter Bot as a background service, follow these steps:

1. **Create a Systemd Service File**:
   - A service file `bot.service` has been created in the project directory.
   - Ensure the `User` field in the service file matches your system username.

2. **Copy the Service File**:
   ```bash
   sudo cp bot.service /etc/systemd/system/
   ```

3. **Start the Service**:
   ```bash
   sudo systemctl start bot
   ```

4. **Enable Auto-start**:
   ```bash
   sudo systemctl enable bot
   ```

5. **Check Status**:
   ```bash
   sudo systemctl status bot
   ```

## Error Handling

The bot includes comprehensive error handling:

- **Network Issues**: Automatically retries failed downloads/uploads
- **File Corruption**: Uses temporary files to prevent data corruption
- **Progress Tracking**: Shows detailed progress for long operations
- **Cleanup**: Automatically removes temporary files
- **User Limits**: Preserves user access limits on failed operations

## Bot Commands

### General Commands
- `/start` - Start the bot and get usage instructions
- `/getid` - Get your Telegram user ID
- `/checklimit` - Check your remaining access limit
- `/create_txt` - Create a text file for conversion
- `/merge_vcf` - Start merging multiple VCF files

### File Conversion Methods
1. **Direct File Upload**:
   - Upload a TXT file directly to convert to VCF
   - Upload an Excel (XLSX) file directly to convert to VCF

2. **Command-based Conversion**:
   - `/txt_to_vcf` - Start TXT to VCF conversion process
   - `/excel_to_vcf` - Start Excel to VCF conversion process

### Owner Commands
- `/whitelist` - View all whitelisted users and their access limits
- `/add <user_id>` - Add a user to the whitelist
- `/remove <user_id>` - Remove a user from the whitelist
- `/setlimit <user_id> <limit>` - Set access limit for a user
- `/add_owner <user_id>` - Add a new owner (only owners can add new owners)
- `/remove_owner <user_id>` - Remove an owner (cannot remove the last owner)
- `/list_owners` - View all current owners
- `/broadcast <message>` - Send a message to all whitelisted users
- `/restart` - Restart the bot

### File Conversion Features
1. **File Format Support**:
   - Convert TXT files to VCF
   - Convert Excel (XLSX) files to VCF
   - Merge multiple VCF files into one

2. **Customization Options**:
   - Split output into multiple files
   - Set number of contacts per file
   - Customize file sequence numbers
   - Custom output filenames

3. **VCF File Management**:
   - Merge multiple VCF files
   - Custom naming for merged files
   - Automatic file splitting

### Access Control System
- **Multiple Owners**:
  - Share bot management with multiple owners
  - All owners have full administrative privileges
  - Cannot remove the last remaining owner

- **User Management**:
  - Whitelist-based access control
  - Per-user access limits
  - Access limit checking and tracking

### Usage Examples

1. **Converting Files**:
   - Upload a TXT or Excel file directly
   - Use `/txt_to_vcf` or `/excel_to_vcf` commands
   - Follow the bot's prompts to customize the conversion

2. **Managing Users**:
   ```
   /add 123456789        # Add user to whitelist
   /setlimit 123456789 5 # Set 5 uses limit
   /remove 123456789     # Remove from whitelist
   ```

3. **Owner Management**:
   ```
   /add_owner 123456789  # Add new owner
   /list_owners          # View all owners
   /remove_owner 123456789  # Remove an owner
   ```

4. **Merging VCF Files**:
   ```
   /merge_vcf           # Start merge process
   [Upload VCF files]   # Upload files to merge
   /done               # Finish uploading
   [Enter filename]    # Set output filename
   ```

## Dependencies

- python-telegram-bot: Telegram Bot API wrapper
- pandas: Data manipulation and analysis
- openpyxl: Excel file handling
- python-dotenv: Environment variable management
- async-timeout: Async operation timeouts
- watchdog: File system monitoring
- aiohttp: Async HTTP client/server
- Additional dependencies in requirements.txt

## Support

For issues or feature requests, please contact the bot owner through Telegram.
