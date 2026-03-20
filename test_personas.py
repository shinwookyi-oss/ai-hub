import os
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(url, key)

print("Testing user_personas table...")
try:
    res = supabase.table("user_personas").select("*").limit(1).execute()
    print("user_personas table exists!")
except Exception as e:
    print(f"Error accessing user_personas: {e}")
    print("We should save custom personas in the users table using a new JSONB column 'custom_personas', or just use localStorage.")
    
try:
    res = supabase.table("users").select("custom_personas").limit(1).execute()
    print("users.custom_personas exists!")
except Exception as e:
    print(f"Error accessing users.custom_personas: {e}")
