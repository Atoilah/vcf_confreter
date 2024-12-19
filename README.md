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

- `/start` - Start the bot and get usage instructions
- `/getid` - Get your Telegram user ID
- `/checklimit` - Check your remaining access limit
- `/create_txt` - Create a text file for conversion

**Admin Commands**:
- `/whitelist` - View whitelisted users
- `/add_whitelist` - Add a user to whitelist
- `/remove_whitelist` - Remove a user from whitelist
- `/set_limit` - Set access limit for a user
- `/view_logs` - View user interaction logs
- `/broadcast` - Send message to all users
- `/restart` - Restart the bot

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
