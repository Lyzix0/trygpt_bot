from pathlib import Path
import yaml
import sys

sys.setrecursionlimit(10000)
group_id = -1001924365194
start_text = """Привет, я чат-бот с нейросетью ChatGPT

Чтобы начать отправлять запросы, Вам
необходимо быть подписанным на наш
Telegram - канал TryChatGPT"""

help_text = """<b>О боте</b>

Чат-бот c нейросетью ChatGPT 
от команды сервиса TryChatGPT.ru

<b>Лимиты</b>

Бесплатно:
15 запросов в сутки

<b>В подписке Plus:</b>
Безлимитные запросы

Чтобы использовать бота без ограничений, вы можете приобрести подписку по команде /pay

Написать в поддержку — @trygptsupport
Режим работы: 10:00 - 23:00 по МСК"""

sub_true_message = """Привет! 👋 Я рад, что ты решил попробовать бота TryChatGPT в Telegram! 🤖 Вот некоторые команды:

/start - Перезапуск
/new - Начать новый диалог
/info - Мой аккаунт
/pay - Тарифы
/help - Помощь

В бесплатной версии Вам доступно 15 запросов в сутки. Чтобы начать, отправь свой запрос боту, и он ответит на него с использованием передовых технологий искусственного интеллекта. 
Если у тебя есть вопросы, не стесняйся задавать! Я здесь, чтобы помочь."""


config_dir = Path(__file__).parent.parent.resolve() / "configs"

with open(config_dir / "config.yml", "r", encoding="utf-8") as f:
    config_yaml = yaml.safe_load(f)

yoomoney_token = config_yaml["yoomoney_token"]

with open(config_dir / "openAI_tokens.txt", "r") as f:
    apiKeys = f.read().split("\n")

n_chat_modes_per_page = config_yaml.get("n_chat_modes_per_page", 5)

with open(config_dir / "chat_modes.yml", "r", encoding="utf-8") as f:
    chat_modes = yaml.safe_load(f)
with open(config_dir / "models.yml", "r", encoding="utf-8") as f:
    models = yaml.safe_load(f)
