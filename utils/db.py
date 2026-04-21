from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

class SupabaseDB:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
    
    def get_client(self):
        return self.client

db = SupabaseDB()
