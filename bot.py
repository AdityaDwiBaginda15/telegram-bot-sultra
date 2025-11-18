import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import requests
import json
import logging
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def debug_environment():
    """Debug comprehensive environment"""
    logging.info("🔍 === RAILWAY ENVIRONMENT DEBUG ===")
    
    # List ALL environment variables (mask sensitive ones)
    all_vars = dict(os.environ)
    logging.info(f"📋 Total environment variables: {len(all_vars)}")
    
    for key, value in all_vars.items():
        if any(secret in key.lower() for secret in ['token', 'key', 'credential', 'password']):
            logging.info(f"   {key}: [HIDDEN - LENGTH: {len(value)}]")
        else:
            logging.info(f"   {key}: {value}")
    
    # Check our specific variables
    our_vars = {
        'TELEGRAM_BOT_TOKEN': os.getenv('TELEGRAM_BOT_TOKEN'),
        'TELEGRAM_CHAT_IDS': os.getenv('TELEGRAM_CHAT_IDS'),
        'SPREADSHEET_URL': os.getenv('SPREADSHEET_URL'),
        'GOOGLE_CREDENTIALS_JSON': os.getenv('GOOGLE_CREDENTIALS_JSON')
    }
    
    logging.info("🔍 === OUR VARIABLES DEBUG ===")
    for key, value in our_vars.items():
        exists = value is not None
        length = len(value) if exists else 0
        logging.info(f"   {key}: EXISTS={exists}, LENGTH={length}")
        
        if exists and key == 'GOOGLE_CREDENTIALS_JSON':
            try:
                json.loads(value)
                logging.info(f"   {key}: ✅ VALID JSON")
            except json.JSONDecodeError as e:
                logging.info(f"   {key}: ❌ INVALID JSON: {e}")
    
    return our_vars

class RailwaySpreadsheetMonitor:
    def __init__(self):
        # Debug first
        self.debug_vars = debug_environment()
        
        # Get variables
        self.telegram_token = self.debug_vars['TELEGRAM_BOT_TOKEN']
        self.chat_ids = json.loads(self.debug_vars['TELEGRAM_CHAT_IDS']) if self.debug_vars['TELEGRAM_CHAT_IDS'] else []
        self.spreadsheet_url = self.debug_vars['SPREADSHEET_URL']
        self.google_credentials = self.debug_vars['GOOGLE_CREDENTIALS_JSON']
        
        self.previous_row_count = 0
        self.previous_data = []
        
        # Validate
        self.validate_config()
        self.setup_google_sheets()
        
    def validate_config(self):
        """Validate configuration"""
        missing = [k for k, v in self.debug_vars.items() if not v]
        if missing:
            error_msg = f"Missing: {', '.join(missing)}"
            logging.error(f"❌ {error_msg}")
            raise ValueError(error_msg)
        logging.info("✅ All environment variables are set")
    
    def setup_google_sheets(self):
        """Setup Google Sheets"""
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds_dict = json.loads(self.google_credentials)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            logging.info("✅ Google Sheets API setup successfully")
        except Exception as e:
            logging.error(f"❌ Google Sheets setup failed: {e}")
            raise

    # ... (rest of the methods remain the same as previous working version)
    def get_sultra25_data(self):
        """Get data from Sultra-25 sheet"""
        try:
            spreadsheet = self.client.open_by_url(self.spreadsheet_url)
            worksheet = spreadsheet.worksheet("Sultra-25")
            all_data = worksheet.get_all_values()
            
            relevant_data = []
            for i, row in enumerate(all_data):
                if i >= 3 and len(row) >= 8:
                    has_number = len(row) > 0 and row[0] and row[0].strip() and row[0].isdigit()
                    has_customer = len(row) > 5 and row[5] and row[5].strip()
                    
                    if has_number and has_customer:
                        relevant_data.append({
                            'no': row[0],
                            'customer_name': row[5],
                            'segment': row[6] if len(row) > 6 else "",
                            'am_hotda': row[7] if len(row) > 7 else ""
                        })
            
            logging.info(f"📊 Data found: {len(relevant_data)} valid rows")
            return relevant_data, len(relevant_data)
            
        except Exception as e:
            logging.error(f"❌ Error accessing spreadsheet: {e}")
            return [], 0
    
    def find_new_rows(self, current_data, current_row_count):
        """Find newly added rows"""
        if self.previous_row_count == 0:
            self.previous_row_count = current_row_count
            self.previous_data = current_data
            if current_data:
                last_number = current_data[-1]['no']
                logging.info(f"📋 Last valid row: {last_number}")
                logging.info(f"🎯 Waiting for row: {int(last_number) + 1}")
            return []
        
        new_rows = []
        if current_row_count > self.previous_row_count:
            new_row_count = current_row_count - self.previous_row_count
            new_rows = current_data[-new_row_count:]
            logging.info(f"🎉 Detected {new_row_count} new row(s)")
        
        self.previous_row_count = current_row_count
        self.previous_data = current_data
        return new_rows
    
    def send_telegram_message(self, message, chat_id):
        """Send message to Telegram"""
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logging.error(f"Error sending to {chat_id}: {e}")
            return False
    
    def send_multiple_notifications(self, message):
        """Send to all chat IDs"""
        success_count = 0
        for chat_id in self.chat_ids:
            if self.send_telegram_message(message, chat_id):
                success_count += 1
                logging.info(f"✅ Sent to chat ID: {chat_id}")
            else:
                logging.error(f"❌ Failed to send to chat ID: {chat_id}")
        return success_count
    
    def format_notification(self, entry):
        """Format notification message"""
        message = f"🆕 **Ada LOP baru dari Sultra-25:**\n"
        message += f"🔢 **No:** {entry['no']}\n"
        message += f"👤 **Nama Pelanggan:** {entry['customer_name']}\n"
        message += f"🏢 **SEGMEN:** {entry['segment']}\n" 
        message += f"🤵 **AM/HOTDA:** {entry['am_hotda']}\n"
        message += f"📊 **Status:** LOP Baru"
        return message
    
    def start_monitoring(self):
        """Start 24/7 monitoring"""
        logging.info("🚀 Starting Sultra-25 Monitor on Railway...")
        logging.info(f"👥 Monitoring for {len(self.chat_ids)} chat IDs")
        logging.info("⏰ 24/7 Real-time monitoring ACTIVE")
        
        initial_data, initial_count = self.get_sultra25_data()
        self.previous_row_count = initial_count
        self.previous_data = initial_data
        logging.info(f"✅ Initial load: {initial_count} rows")
        
        error_count = 0
        
        while True:
            try:
                current_data, current_count = self.get_sultra25_data()
                new_entries = self.find_new_rows(current_data, current_count)
                
                for entry in new_entries:
                    notification = self.format_notification(entry)
                    success_count = self.send_multiple_notifications(notification)
                    logging.info(f"📨 Sent {success_count}/{len(self.chat_ids)} for: {entry['no']}. {entry['customer_name']}")
                
                error_count = 0
                time.sleep(15)
                
            except Exception as e:
                error_count += 1
                logging.error(f"Error #{error_count}: {e}")
                
                if error_count >= 5:
                    logging.error("🔄 Too many errors, waiting 5 minutes...")
                    time.sleep(300)
                    error_count = 0
                else:
                    time.sleep(60)

def main():
    try:
        monitor = RailwaySpreadsheetMonitor()
        monitor.start_monitoring()
    except Exception as e:
        logging.error(f"❌ Failed to start monitor: {e}")
        exit(1)

if __name__ == "__main__":
    main()

