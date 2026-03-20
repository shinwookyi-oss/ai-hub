import os
import sys
from dotenv import load_dotenv

# Load standard .env if needed
load_dotenv()

# Set up supabase client same as app
from supabase import create_client, Client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY")
    sys.exit(1)

supabase: Client = create_client(url, key)

print("Checking user shinwookyi...")
res = supabase.table("users").select("id, tier").eq("username", "shinwookyi").execute()
if len(res.data) > 0:
    user_id = res.data[0]["id"]
    print(f"Found shinwookyi: {res.data[0]}")
    print("Upgrading to owner...")
    
    try:
        update_res = supabase.table("users").update({"tier": "owner"}).eq("id", user_id).execute()
        print("Upgrade successful!")
    except Exception as e:
        print(f"Failed to upgrade: {e}")
        
    print("Testing if we can save email/phone...")
    try:
        supabase.table("users").update({"email": "test@test.com", "phone": "12345"}).eq("id", user_id).execute()
        print("Success! email and phone columns exist.")
    except Exception as e:
        print(f"Failed to set email/phone: {e}")
        print("Columns probably do not exist.")
else:
    print("User shinwookyi not found.")
