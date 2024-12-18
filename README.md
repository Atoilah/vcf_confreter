# Telegram Contact Converter Bot

A Telegram bot that converts text and Excel files to VCF (vCard) format.

## Features

- Convert TXT files to VCF format
- Convert Excel (XLSX) files to VCF format
- User access control with whitelist
- Access limit management per user
- Customizable contact naming patterns
- Split output into multiple VCF files
- Handles NaN values in Excel files gracefully
- Improved error handling and user notifications

## New Features

- **Junk File Cleaning**: Owners can clean up junk files and logs to maintain the bot's efficiency.
- **Bot Restart**: Owners can restart the bot via a Telegram command.
- **Broadcast Messages**: Owners can send broadcast messages to all users via a Telegram command.

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
   - Copy the `bot.service` file to the systemd directory:
     ```bash
     sudo cp /home/.../bot_tele/payment/vcf_confreter/bot.service /etc/systemd/system/
     ```

3. **Reload Systemd**:
   - Reload the systemd daemon to recognize the new service:
     ```bash
     sudo systemctl daemon-reload
     ```

4. **Start the Service**:
   - Start the bot service:
     ```bash
     sudo systemctl start bot.service
     ```

5. **Enable the Service**:
   - Enable the service to start on boot:
     ```bash
     sudo systemctl enable bot.service
     ```

6. **Check Service Status**:
   - Check the status of the service to ensure it's running:
     ```bash
     sudo systemctl status bot.service
     ```

7. **Remove the Service**:
   - If you no longer need the bot to run as a service, you can remove it:
     ```bash
     sudo systemctl stop bot.service
     sudo systemctl disable bot.service
     sudo rm /etc/systemd/system/bot.service
     sudo systemctl daemon-reload
     sudo systemctl reset-failed
     ```
   - This will stop the service, prevent it from starting on boot, and remove the service file.

This setup will ensure your bot runs continuously in the background and restarts automatically if it crashes or the system reboots.

## Usage

- Upload a TXT or Excel file to convert it to VCF format.
- Follow the prompts to customize the output.

## File Format Requirements

### TXT Files
- Each line should contain either:
  - Just a phone number
  - Name and phone number separated by comma

### Excel Files
- First column should contain phone numbers
- Numbers can be with or without country code
- Bot will automatically add '+' if missing

## Security Features

- Bot token and owner ID stored in environment variables
- User whitelist stored in JSON file
- Access limits per user
- Only owner can manage users and limits
- Owner can restart the bot and broadcast messages
