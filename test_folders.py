import os
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

print("Checking and adding parent_id to folders table...")
try:
    # Try an insert to see if parent_id exists
    res = supabase.table("folders").select("parent_id").limit(1).execute()
    print("parent_id exists!")
except Exception as e:
    print(f"parent_id doesn't exist or error: {e}")
    # We can't do DDL (ALTER TABLE) easily through PostgREST. The user has to do it!
