import os
import sys
from dotenv import load_dotenv

# Load env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print("=========================================")
print("NHT ATHENA SUPABASE CONFIGURATION DIAGNOSTIC")
print("=========================================")
print(f"Supabase URL: {supabase_url}")
print(f"Supabase Key configured: {'YES (Length: ' + str(len(supabase_key)) + ')' if supabase_key else 'NO'}")
print("-----------------------------------------")

if not supabase_url or not supabase_key:
    print("[ERROR] Missing SUPABASE_URL or SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY in .env file.")
    print("Please make sure these are defined. For example:")
    print("SUPABASE_URL=https://your-project-id.supabase.co")
    print("SUPABASE_KEY=your-anon-or-service-role-key")
    sys.exit(1)

try:
    from supabase import create_client, Client
    supabase: Client = create_client(supabase_url, supabase_key)
    print("[SUCCESS] Successfully imported and initialized Supabase client.")
    
    # Safety check: Verify connection & table status without dropping anything
    tables = ["briefs", "feedback", "drafts", "priorities", "rl_signals", "offline_queue", "oauth_tokens"]
    existing_tables = []
    missing_tables = []
    
    print("\nChecking database tables (Safety Check: No DROP statements will be executed)...")
    for table in tables:
        try:
            # Query 0 items to check table existence
            supabase.table(table).select("*").limit(0).execute()
            existing_tables.append(table)
            print(f"  - Table '{table}': [EXISTS] (No action needed)")
        except Exception:
            missing_tables.append(table)
            print(f"  - Table '{table}': [MISSING or UNREACHABLE]")

    if missing_tables:
        print("\n[INFO] Some tables are missing. To create them safely without dropping any existing tables:")
        print("1. Open your Supabase Dashboard (https://supabase.com).")
        print("2. Navigate to the SQL Editor.")
        print("3. Copy the DDL statements from 'scratch/migrations.sql' (uses CREATE TABLE IF NOT EXISTS).")
        print("4. Click Run.")
    else:
        print("\n[SUCCESS] All tables are created and accessible. Safe to run. No tables were modified or dropped.")
        
except Exception as e:
    print(f"[ERROR] Failed to initialize Supabase client or connect: {e}")
    sys.exit(1)
