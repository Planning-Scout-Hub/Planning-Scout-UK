import gspread
import json
import os
from google.oauth2.service_account import Credentials

# 1. SETUP AUTH
def get_gc():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Uses the same secret as your engine
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
    return gspread.authorize(creds)

def distribute():
    gc = get_gc()
    
    # 2. LOAD MASTER DATA
    # Replace with your actual Master Sheet ID
    master_sheet = gc.open_by_key("YOUR_MASTER_SHEET_ID_HERE").get_worksheet(0)
    master_records = master_sheet.get_all_records()
    
    # 3. DEFINE CLIENTS TO PROCESS
    client_files = ["aynsley_planning.json", "maplanning.json"]
    
    for file in client_files:
        with open(file, "r") as f:
            config = json.load(f)
        
        target_sheet = gc.open_by_key(config["sheet_id"]).get_worksheet(0)
        existing_urls = target_sheet.col_values(3) # Assumes URL is in column C
        
        print(f"--- Processing {config['client_name']} ---")
        
        for row in master_records:
            # Skip if client already has this lead
            if row['Application URL'] in existing_urls:
                continue
                
            text = row.get('Decision Text', '').lower()
            score = 0
            
            # KEYWORD MATCHING
            matches = [k for k in config['search_keywords'] if k.lower() in text]
            score += len(matches) * 10
            
            # PDF TRIGGER MATCHING
            triggers = [t for t in config['pdf_triggers'] if t.lower() in text]
            score += len(triggers) * 15
            
            # ADVANCED SCORING (The "John Specials")
            if "tilted balance" in text: score += 50
            if "contrary to officer" in text: score += 100
            
            # QUALIFICATION
            if score >= config['min_lead_score']:
                print(f"✅ Lead Qualified (Score: {score}): {row['Address']}")
                # Append to client sheet (convert dict values to list)
                target_sheet.append_row(list(row.values()))

if __name__ == "__main__":
    distribute()
