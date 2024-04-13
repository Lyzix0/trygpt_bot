import json
import logging
import random

import aiohttp
import configuration as config


OPENAI_OPTIONS = {
    "temperature": 0.7,
    "max_tokens": 500,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "request_timeout": 60.0,
}

# ИСПОЛЬЗОВАНИЕ ПРОКСИ ОБЯЗАТЕЛЬНО!!! OPENAI запретил из россии отправлять запросы.
PROXY_END_POINT = config.config_yaml['PROXY_END_POINT']
USERNAME = config.config_yaml['USERNAME']
PASSWORD = config.config_yaml['PASSWORD']


class ChatGPT:
    def __init__(self, model="gpt-3.5-turbo-1106"):
        self.current_key = config.apiKeys[random.randint(0, len(config.apiKeys) - 1)]
        assert (
            model in config.models["available_text_models"]
        ), f"Unknown model: {model}"
        self.model = model

    async def send_message(
        self, message, dialog_messages=[], chat_mode="assistant", k: int = 0
    ):
        messages = self._generate_prompt_messages(
            message, dialog_messages, chat_mode, True
        )

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.current_key}",
        }

        payload = {"model": self.model, "messages": messages}

        if k == 20:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    proxy=f"http://{USERNAME}:{PASSWORD}@{PROXY_END_POINT}",
                    timeout=60,
                ) as response:
                    response = await response.json()

            answer = response["choices"][0]["message"]["content"]
            return answer

        except Exception as e:
            logging.log(logging.WARNING, e)
            k += 1
            self.current_key = config.apiKeys[
                random.randint(0, len(config.apiKeys) - 1)
            ]
            return await self.send_message(message, dialog_messages, chat_mode, k)

    @staticmethod
    def _generate_prompt_messages(
            message, dialog_messages, chat_mode, in_dialogue: bool = True
    ):
        prompt = config.chat_modes[chat_mode]["prompt_start"]

        messages = [{"role": "system", "content": prompt}]
        if dialog_messages and in_dialogue:
            for dialog_message in dialog_messages:
                messages.append({"role": "user", "content": dialog_message["user"]})
                messages.append({"role": "assistant", "content": dialog_message["bot"]})
        messages.append({"role": "user", "content": message})

        return messages

    @staticmethod
    def _postprocess_answer(answer):
        answer = answer.strip()
        return answer
