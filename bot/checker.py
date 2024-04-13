import asyncio
import json
import aiohttp
import configuration as config


PROXY_END_POINT = config.config_yaml['PROXY_END_POINT']
USERNAME = config.config_yaml['USERNAME']
PASSWORD = config.config_yaml['PASSWORD']


def load_api_keys(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file.readlines()]


async def check_and_write_keys(api_keys, working_keys_file, non_working_keys_file):
    working_keys = []
    with open(non_working_keys_file, "a") as non_working_file:
        for api_key in api_keys:
            current_api_key = api_key
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "temperature": 0.1,
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers=headers,
                        data=json.dumps(payload),
                        proxy=f"http://{USERNAME}:{PASSWORD}@{PROXY_END_POINT}",
                        timeout=10,
                    ) as response:
                        response = await response.json()

                ans = response["choices"][0]["message"]["content"]
                if ans:
                    working_keys.append(current_api_key)
                    print(current_api_key, "works")
            except Exception:
                print(response)
                print(current_api_key, "not working")
                non_working_file.write(f"{current_api_key}\n")

    with open(working_keys_file, "w") as f:
        for key in working_keys:
            f.write(f"{key}\n")

    print("Проверка ключей закончена!")


if __name__ == "__main__":
    api_keys_file = "../configs/openAI_tokens.txt"
    working_keys_file = "../configs/openAI_tokens.txt"
    non_working_keys_file = "logs/not_working.txt"

    api_keys = load_api_keys(api_keys_file)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        check_and_write_keys(api_keys, working_keys_file, non_working_keys_file)
    )
