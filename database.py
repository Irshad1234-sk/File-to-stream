# database.py

import motor.motor_asyncio
from config import Config


class Database:
    def __init__(self):
        self._client = None
        self.db = None
        self.collection = None

    async def connect(self):
        """MongoDB se connect karta hai. Fail hone par bhi app band nahi hoti."""
        if not Config.DATABASE_URL:
            print("WARNING: DATABASE_URL set nahi hai. Links save nahi honge.")
            return
        if "<db_username>" in Config.DATABASE_URL or "<db_password>" in Config.DATABASE_URL:
            print("!!! DATABASE_URL me <db_username>/<db_password> placeholder abhi bhi hai. Asli username/password daalo.")
        try:
            print("Connecting to the database...")
            self._client = motor.motor_asyncio.AsyncIOMotorClient(
                Config.DATABASE_URL, serverSelectionTimeoutMS=8000
            )
            await self._client.admin.command("ping")
            self.db = self._client["StreamLinksDB"]
            self.collection = self.db["links"]
            print("✅ Database connection established.")
        except Exception as e:
            print(f"!!! DATABASE ERROR: {e}")
            print("    Check: username/password, Atlas me Network Access = 0.0.0.0/0")
            # collection phir bhi set rakho taaki baad me retry ho sake
            if self._client is not None:
                self.db = self._client["StreamLinksDB"]
                self.collection = self.db["links"]

    async def disconnect(self):
        if self._client:
            self._client.close()
            print("Database connection closed.")

    async def save_link(self, unique_id, message_id):
        if self.collection is None:
            raise RuntimeError("Database connected nahi hai (DATABASE_URL check karo).")
        await self.collection.insert_one({"_id": unique_id, "message_id": message_id})

    async def get_link(self, unique_id):
        if self.collection is None:
            return None
        doc = await self.collection.find_one({"_id": unique_id})
        return doc.get("message_id") if doc else None


db = Database()
