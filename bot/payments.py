import uuid
import aiohttp
import database


class Payments:
    def __init__(self, account_id: str, secret_key: str, db: database):
        self.days_dict = {120: 1, 200: 7, 400: 30}
        self.db = database.Database
        self.account_id = account_id
        self.secret_key = secret_key
        self.db = db

    async def create_payment(self, user_id: int, amount: int):
        url = "https://api.yookassa.ru/v3/payments"
        headers = {
            "Idempotence-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }
        auth = aiohttp.BasicAuth(self.account_id, self.secret_key)

        data = {
            "amount": {"value": amount, "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/trychatgptru_bot",
            },
            "description": "Подписка в Telegram боте",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, auth=auth, json=data
            ) as response:
                result = await response.json()

        await self.db.create_payment(result["id"], user_id, self.days_dict[amount])
        return result

    async def check_payment(self, payment_id: str):
        url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
        auth = aiohttp.BasicAuth(self.account_id, self.secret_key)

        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth) as response:
                response = await response.json()

        return response
