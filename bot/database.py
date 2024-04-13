import uuid
from datetime import datetime
from typing import Optional, Any
import configs
from motor import motor_asyncio


class Database:
    def __init__(self):
        self.uri = "mongodb+srv://Lyzix:eLTdwatIxXoCzESH@db1.zd0t74q.mongodb.net/?retryWrites=true&w=majority"
        self.client = motor_asyncio.AsyncIOMotorClient(self.uri)
        self.db = self.client["chatgpt_telegram_bot"]

        self.user_collection = self.db["user"]
        self.dialog_collection = self.db["dialog"]
        self.payments_collection = self.db["payments"]

    async def check_if_user_exists(self, user_id: int, raise_exception: bool = False):
        if await self.user_collection.count_documents({"chat_id": user_id}) > 0:
            return True
        else:
            if raise_exception:
                raise ValueError(f"User {user_id} does not exist")
            else:
                return False

    async def add_new_user(
        self,
        user_id: int,
        username: str = "",
    ):
        user_dict = {
            "_id": user_id,
            "chat_id": user_id,
            "username": username,
            "last_interaction": datetime.now(),
            "current_dialog_id": None,
            "current_chat_mode": "assistant",
            "current_model": configs.models["available_text_models"][0],
            "available_prompts": 15,
            "subscriber": False,
            "to_subscribe_date": datetime.now(),
        }

        if not await self.check_if_user_exists(user_id):
            await self.user_collection.insert_one(user_dict)

    async def start_new_dialog(self, user_id: int, name):
        await self.check_if_user_exists(user_id, raise_exception=True)

        dialog_id = str(uuid.uuid4())

        chat_mode = await self.get_user_attribute(user_id, "current_chat_mode")
        model = await self.get_user_attribute(user_id, "current_model")

        dialog_dict = {
            "name": name,
            "_id": dialog_id,
            "user_id": user_id,
            "chat_mode": chat_mode,
            "start_time": datetime.now(),
            "model": model,
            "messages": [],
        }
        await self.dialog_collection.insert_one(dialog_dict)

        await self.user_collection.update_one(
            {"chat_id": user_id}, {"$set": {"current_dialog_id": dialog_id}}
        )

        return dialog_id

    async def create_payment(self, payment_id: str, user_id: int, days: int):
        payment_dict = {"_id": payment_id, "user_id": user_id, "days": days}
        await self.payments_collection.insert_one(payment_dict)

    async def get_user_attribute(self, user_id: int, key: str):
        await self.check_if_user_exists(user_id, raise_exception=True)
        user_dict = await self.user_collection.find_one({"chat_id": user_id})

        if key not in user_dict:
            return None

        return user_dict[key]

    async def get_user_dialogs(self, user_id: int, key: str = None):
        await self.check_if_user_exists(user_id, raise_exception=True)
        dialog_dict = self.dialog_collection.find({"user_id": user_id})

        dialogs = []
        async for doc in dialog_dict:
            if key:
                dialogs.append(doc[key])
            else:
                dialogs.append(doc)

        return dialogs

    async def get_dialog_attribute(self, dialog_id: str = None, key: str = "user_id"):
        user_dict = await self.dialog_collection.find_one({"_id": dialog_id})

        if key not in user_dict:
            return None

        return user_dict[key]

    async def set_user_attribute(self, user_id: int, key: str, value: Any):
        await self.check_if_user_exists(user_id, raise_exception=True)
        await self.user_collection.update_one(
            {"chat_id": user_id}, {"$set": {key: value}}
        )

    async def get_dialog_messages(self, user_id: int, dialog_id: Optional[str] = None):
        await self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = await self.get_user_attribute(user_id, "current_dialog_id")

        dialog_dict = await self.dialog_collection.find_one(
            {"_id": dialog_id, "user_id": user_id}
        )

        if dialog_dict:
            return dialog_dict["messages"]

    async def set_dialog_messages(
        self, user_id: int, dialog_messages: list, dialog_id: Optional[str] = None
    ):
        await self.check_if_user_exists(user_id, raise_exception=True)

        if dialog_id is None:
            dialog_id = await self.get_user_attribute(user_id, "current_dialog_id")

        await self.dialog_collection.update_one(
            {"_id": dialog_id, "user_id": user_id},
            {"$set": {"messages": dialog_messages}},
        )
