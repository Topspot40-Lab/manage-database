from backend.services.supabase_client import supabase

buckets = supabase.storage.list_buckets()
print(f"📦 Buckets: {buckets}")
