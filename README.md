# Telegram Contact Converter Bot

A Telegram bot that converts text and Excel files to VCF (vCard) format.

## Features

- Convert TXT files to VCF format
- Convert Excel (XLSX) files to VCF format
- User access control with whitelist
- Access limit management per user
- Customizable contact naming patterns
- Split output into multiple VCF files

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following content:
   ```
   BOT_TOKEN=your_bot_token_here
   OWNER_ID=your_telegram_user_id
   ```
   Replace `your_bot_token_here` with your Telegram bot token and `your_telegram_user_id` with your Telegram user ID.

## Usage

1. Start the bot:
   ```bash
   python bot.py
   ```

2. Available commands:
   - `/start` - Start the bot and see available commands
   - `/getid` - Get your Telegram user ID
   - `/checklimit` - Check your remaining access limit
   - `/txt_to_vcf` - Convert TXT file to VCF
   - `/excel_to_vcf` - Convert Excel file to VCF

   Admin commands:
   - `/add <user_id>` - Add user to whitelist
   - `/remove <user_id>` - Remove user from whitelist
   - `/setlimit <user_id> <limit>` - Set user's access limit
   - `/whitelist` - Show all whitelisted users

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
