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
   python bot.py
   ```

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
