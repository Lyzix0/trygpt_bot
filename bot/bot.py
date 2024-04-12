import asyncio
import logging
from datetime import datetime, timedelta

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import configuration as config
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
import openai
import database
from checker import load_api_keys, check_and_write_keys
from payments import Payments
from chatgpt import ChatGPT

dp = Dispatcher()
db = database.Database()
payments = Payments(
    config.config_yaml["yoomoney_id"], config.config_yaml["yoomoney_token"], db
)
bot = Bot(config.config_yaml["telegram_token"], parse_mode=ParseMode.HTML)
router = Router()

sub_button1 = InlineKeyboardButton(text="400₽ за 30 дней", callback_data="pay|30|400")
sub_button2 = InlineKeyboardButton(text="200₽ за 7 дней", callback_data="pay|7|200")
sub_button3 = InlineKeyboardButton(text="120₽ за 1 день", callback_data="pay|1|120")
donate_button = InlineKeyboardButton(
    text="Поддержать проект", url="https://pay.cloudtips.ru/p/acb4c399"
)
reply_markup_sub = InlineKeyboardMarkup(
    inline_keyboard=[[sub_button1], [sub_button2], [sub_button3], [donate_button]]
)

profile_button = KeyboardButton(text="Мой аккаунт")
new_dialogue_button = KeyboardButton(text="Новый диалог")
tariffs_button = KeyboardButton(text="Тарифы")
dialogs_button = KeyboardButton(text="Мои диалоги")
help_button = KeyboardButton(text="Поддержка")
keyboard_profile = ReplyKeyboardMarkup(
    keyboard=[
        [profile_button, tariffs_button],
        [dialogs_button, new_dialogue_button],
        [help_button],
    ],
    resize_keyboard=True,
)


class Form(StatesGroup):
    type_name = State()


@dp.message(CommandStart())
async def command_start_handler(message: Message):
    await register_user_if_not_exists(message)

    photo = FSInputFile("start_photo.jpg")
    button_channel = InlineKeyboardButton(
        text="Перейти в канал", url="https://t.me/chatgpt_try"
    )
    button_check = InlineKeyboardButton(text="Я подписан", callback_data="check_sub")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button_channel], [button_check]])

    if not await is_subscriber_channel(message.from_user.id):
        await bot.send_photo(
            chat_id=message.from_user.id,
            photo=photo,
            caption=config.start_text,
            reply_markup=keyboard,
        )
    else:
        await bot.send_message(
            chat_id=message.from_user.id,
            text=config.sub_true_message,
            reply_markup=keyboard_profile,
        )


@dp.message(F.text == "Поддержка")
@dp.message(Command("help"))
async def help_handle(message: types.Message):
    await register_user_if_not_exists(message)
    await message.reply(
        config.help_text, parse_mode=ParseMode.HTML, reply_markup=keyboard_profile
    )


async def get_user_info(message: Message = None, callback: CallbackQuery = None):
    if message:
        user = message.from_user
        user_id = message.from_user.id
    else:
        user = callback.from_user
        user_id = callback.from_user.id

    button_dialogs = InlineKeyboardButton(text="Мои диалоги", callback_data="dialogs")
    sub_menu_button = InlineKeyboardButton(
        text="Управление подпиской", callback_data="subscribe"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[button_dialogs], [sub_menu_button]]
    )

    sub = await db.get_user_attribute(user_id, "subscriber")
    prompts = await db.get_user_attribute(user_id, "available_prompts")

    hello_part = f"""Привет, {user.username}!\nНадеюсь, у тебя всё круто!"""
    if not sub:
        str_sub = "ограниченная"
        text = (
                hello_part
                + f"\n\nID: <b>{user_id}</b>\nПодписка: <b>{str_sub}</b>\n\nЛимиты:\n"
                  f"Осталось бесплатных запросов: <b>{prompts}</b> из 15"
        )
    else:
        str_sub = "безлимитная"
        date_to_sub = await db.get_user_attribute(user_id, "to_subscribe_date")
        date_to_sub = date_to_sub.date()
        days_count = (date_to_sub - datetime.now().date()).days

        days = ["день", "дня", "дней"]
        if days_count % 10 == 1 and days_count % 100 != 11:
            p = 0
        elif 2 <= days_count % 10 <= 4 and (
                days_count % 100 < 10 or days_count % 100 >= 20
        ):
            p = 1
        else:
            p = 2

        days_plur = days[p]
        text = (
                hello_part + f"\n\nID: <b>{user_id}</b>\nПодписка: <b>{str_sub}</b>"
                             f"\nПодписка действительна до <b>{date_to_sub}</b> "
                             f"({days_count} {days_plur})"
        )

    return text, keyboard


@dp.message(F.text == "Мой аккаунт")
@dp.message(Command("info"))
async def my_account(message: types.Message):
    await register_user_if_not_exists(message)
    user_info = await get_user_info(message)
    await bot.send_message(
        chat_id=message.from_user.id,
        text=user_info[0],
        parse_mode=ParseMode.HTML,
        reply_markup=user_info[1],
    )


@router.callback_query(lambda q: q.data == "profile")
async def profile_callback(callback: CallbackQuery):
    await register_user_if_not_exists(callback)
    user_info = await get_user_info(callback=callback)
    await bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        text=user_info[0],
        parse_mode=ParseMode.HTML,
        reply_markup=user_info[1],
    )


async def dialogue_button_creation(user_id: int, message_id: int = None):
    dialogs = await db.get_user_dialogs(user_id, "_id")

    page = 1
    items_per_page = 3
    pages = [
        dialogs[i: i + items_per_page][::-1]
        for i in range(0, len(dialogs), items_per_page)
    ]

    if page > len(pages):
        page = len(pages)

    if not pages:
        await bot.send_message(user_id, text="У вас нет активных диалогов!")
        return

    current_page = pages[page - 1]

    all_buttons = []
    for dialog in current_page:
        name = await db.get_dialog_attribute(dialog, "name")
        time = str(await db.get_dialog_attribute(dialog, "start_time")).split(".")[0]
        time_object = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
        formatted_time = time_object.strftime("%d.%m.%Y")
        all_buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{name} {formatted_time}", callback_data=f"go_dialog|{dialog}"
                )
            ]
        )

    all_buttons.reverse()
    pagination_buttons = []
    sub = await db.get_user_attribute(user_id, "subscriber")
    buttons = []
    if not sub:
        for i in range(min(len(all_buttons), 3)):
            buttons.append(all_buttons[i])
    else:
        buttons = all_buttons

    if len(pages) > 1:
        if page > 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Предыдущая страница⬅️", callback_data=f"prev_page|{page}"
                )
            )
        if page < len(pages):
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Следующая страница➡️", callback_data=f"next_page|{page}"
                )
            )

    profile = InlineKeyboardButton(text="К профилю🖼️", callback_data="profile")
    dialogue_inline = InlineKeyboardButton(
        text="Новый диалог🗣️", callback_data="new_dialogue"
    )
    buttons.append([profile])
    buttons.append([dialogue_inline])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons + [pagination_buttons])

    if not dialogs:
        await bot.send_message(chat_id=user_id, text="У вас нет активных диалогов.")
        return

    if message_id:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=f"Страница {page} из {len(pages)}\n\nТекущие диалоги:",
            reply_markup=reply_markup,
        )
    else:
        await bot.send_message(
            chat_id=user_id,
            text=f"Страница {page} из {len(pages)}\n\nТекущие диалоги:",
            reply_markup=reply_markup,
        )


@dp.message(F.text == "Мои диалоги")
async def dialog_handler(message: Message):
    user_id = message.from_user.id
    await dialogue_button_creation(user_id)


@router.callback_query(lambda q: q.data == "dialogs")
async def dialog_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    await dialogue_button_creation(user_id, callback.message.message_id)


@router.callback_query(lambda q: q.data.startswith(("prev_page", "next_page")))
async def handle_pagination(callback: CallbackQuery):
    user_id = callback.from_user.id
    action, page = callback.data.split("|")
    page = int(page)
    dialogs = await db.get_user_dialogs(user_id, "_id")

    items_per_page = 3
    pages = [
        dialogs[i: i + items_per_page][::-1]
        for i in range(0, len(dialogs), items_per_page)
    ]

    if action == "prev_page":
        page -= 1
    elif action == "next_page":
        page += 1

    if page < 1:
        page = 1
    elif page > len(pages):
        page = len(pages)

    current_page = pages[page - 1]

    all_buttons = []
    for dialog in current_page:
        name = await db.get_dialog_attribute(dialog, "name")
        time = str(await db.get_dialog_attribute(dialog, "start_time")).split(".")[0]
        time_object = datetime.strptime(time, "%Y-%m-%d %H:%M:%S")
        formatted_time = time_object.strftime("%d.%m.%Y")
        all_buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{name} {formatted_time}", callback_data=f"go_dialog|{dialog}"
                )
            ]
        )

    pagination_buttons = []

    sub = await db.get_user_attribute(user_id, "subscriber")
    buttons = []
    if not sub:
        for i in range(min(len(all_buttons), 3)):
            buttons.append(all_buttons[i])
    else:
        buttons = all_buttons

    if len(pages) > 1:
        if page > 1:
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Предыдущая страница⬅️", callback_data=f"prev_page|{page}"
                )
            )
        if page < len(pages):
            pagination_buttons.append(
                InlineKeyboardButton(
                    text="Следующая страница➡️", callback_data=f"next_page|{page}"
                )
            )

    profile = InlineKeyboardButton(text="К профилю🖼️", callback_data="profile")
    dialogue_inline = InlineKeyboardButton(
        text="Новый диалог🗣️", callback_data="new_dialogue"
    )
    buttons.append([profile])
    buttons.append([dialogue_inline])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons + [pagination_buttons])
    await callback.answer()
    await bot.edit_message_text(
        message_id=callback.message.message_id,
        chat_id=user_id,
        text=f"Страница {page} из {len(pages)}\n\nТекущие диалоги:",
        reply_markup=reply_markup,
    )


@router.callback_query(lambda q: q.data.startswith("go_dialog"))
async def callback_select_mode(callback: CallbackQuery):
    await callback.answer()
    user = callback.from_user.id
    dialogue_id = callback.data.split("|")[1]
    chat_mode = await db.get_dialog_attribute(dialogue_id, "chat_mode")

    await db.set_user_attribute(user, "current_dialog_id", dialogue_id)
    if await db.get_dialog_messages(user, dialogue_id):
        last_message = (await db.get_dialog_messages(user, dialogue_id))[-1]["bot"]
        await bot.edit_message_text(
            message_id=callback.message.message_id,
            chat_id=user,
            text=last_message,
            parse_mode="MARKDOWN",
        )
    else:
        await bot.edit_message_text(
            message_id=callback.message.message_id,
            chat_id=user,
            text=config.chat_modes[chat_mode]["welcome_message"],
        )


@dp.message(F.text == "Новый диалог")
@dp.message(Command("new"))
async def new_dialogue(message: Message, state: FSMContext):
    cancel = InlineKeyboardButton(text="Отменить", callback_data="cancel")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[cancel]])
    await message.reply(
        f"""Бот запоминает контекст диалога.\n<b>Введите название диалога:</b>""",
        reply_markup=reply_markup,
    )
    await state.set_state(Form.type_name)


@dp.callback_query(lambda q: q.data == "cancel")
async def cancel_states(callback: CallbackQuery, state: FSMContext):
    await bot.edit_message_text(
        text="Создание диалога отменено!",
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
    )
    await state.clear()


@dp.callback_query(lambda q: q.data == "new_dialogue")
async def new_dialogue_inline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await bot.send_message(
        text=f"""Бот запоминает контекст диалога.\n<b>Введите название диалога:</b>""",
        chat_id=callback.from_user.id,
    )
    await state.set_state(Form.type_name)


@dp.message(F.text == "Тарифы")
@dp.message(Command("pay"))
async def subscribe_select(message: Message):
    await bot.send_message(
        text=f"""Подписка открывает доступ к безлимитному количеству запросов.\n
Eсли Вам достаточно бесплатного тарифа, можете поддержать развитие проекта""",
        chat_id=message.from_user.id,
        reply_markup=reply_markup_sub,
    )


@dp.callback_query(lambda q: q.data == "subscribe")
async def subscribe_select_callback(callback: CallbackQuery):
    await callback.answer()
    await bot.edit_message_text(
        text=f"""Подписка открывает доступ к безлимитному количеству запросов.\n
Eсли Вам достаточно бесплатного тарифа, можете поддержать развитие проекта""",
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        reply_markup=reply_markup_sub,
    )


@router.callback_query(lambda q: q.data.startswith("pay"))
async def proceed_payment(callback: CallbackQuery):
    await callback.answer()
    msg = await bot.send_message(callback.from_user.id, "Создаем ссылку для оплаты...")

    data = callback.data.split("|")
    amount = int(data[2])

    pay_info = await payments.create_payment(callback.from_user.id, amount)
    pay_redirect = pay_info["confirmation"]["confirmation_url"]

    go_button = InlineKeyboardButton(text="Перейти в оплате", url=pay_redirect)
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[go_button]])

    await bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=msg.message_id,
        text=f"""Сумма к оплате составляет {amount} рублей. Подписка автоматически зачислиться на ваш баланс.""",
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


@dp.message(Form.type_name)
async def select_mode(message: Message):
    await db.set_user_attribute(message.from_user.id, "name", message.text)
    text, reply_markup = get_chat_mode_menu(0)
    await bot.send_message(message.from_user.id, text=text, reply_markup=reply_markup)


@router.callback_query(lambda q: q.data.startswith("set_chat_mode"))
async def callback_select_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    chat_mode = callback.data.split("|")[1]
    await db.set_user_attribute(callback.from_user.id, "current_chat_mode", chat_mode)
    name = await db.get_user_attribute(callback.from_user.id, "name")
    await bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        text=f"{config.chat_modes[chat_mode]['welcome_message']}",
        parse_mode=ParseMode.HTML,
    )
    await db.start_new_dialog(name=name, user_id=callback.from_user.id)
    await state.clear()


def get_chat_mode_menu(page_index: int):
    n_chat_modes_per_page = config.n_chat_modes_per_page
    text = f"Выберите <b>режим бота</b> ({len(config.chat_modes)} режимов доступно):"

    chat_mode_keys = list(config.chat_modes.keys())
    page_chat_mode_keys = chat_mode_keys[
                          page_index * n_chat_modes_per_page: (page_index + 1) * n_chat_modes_per_page
                          ]

    keyboard = []
    for chat_mode_key in page_chat_mode_keys:
        name = config.chat_modes[chat_mode_key]["name"]
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=name, callback_data=f"set_chat_mode|{chat_mode_key}"
                )
            ]
        )

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    return text, reply_markup


async def register_user_if_not_exists(message):
    user = message.from_user
    if not await db.check_if_user_exists(user.id):
        await db.add_new_user(user.id, user.username)


@dp.message(F.text.startswith("/"))
async def not_existing_command(message: Message):
    await register_user_if_not_exists(message)
    await message.reply("Такой команды не существует!")


@dp.message()
async def message_handler(message: Message):
    user_id = message.from_user.id
    await register_user_if_not_exists(message)

    text = await bot.send_message(
        user_id, "Генерирую ответ...", disable_notification=True
    )
    future = asyncio.ensure_future(
        change_dots(message_id=text.message_id, chat_id=user_id)
    )

    if not await is_subscriber_channel(message.from_user.id):
        future.cancel()
        button_channel = InlineKeyboardButton(
            text="Перейти в канал", url="https://t.me/chatgpt_try"
        )
        button_check = InlineKeyboardButton(
            text="Я подписан", callback_data="check_sub_prompt"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[button_channel], [button_check]]
        )
        await bot.send_message(
            message.from_user.id,
            """Чтобы начать отправлять запросы, Вам
необходимо быть подписанным на наш
Telegram - канал TryChatGPT""",
            reply_markup=keyboard,
        )
        return

    prompts = await db.get_user_attribute(user_id, "available_prompts")
    sub = await db.get_user_attribute(user_id, "subscriber")

    if prompts <= 0 and not sub:
        future.cancel()
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=text.message_id,
            text="""Упс... К сожалению у вас закончился суточный лимит по запросам\n
Доступно 0 из 15\n
Вы можете оформить подписку и сразу продолжить использование.""",
            reply_markup=reply_markup_sub,
        )
        return

    current_model = await db.get_user_attribute(user_id, "current_model")
    chat_mode = await db.get_user_attribute(user_id, "current_chat_mode")

    chatgpt_instance = ChatGPT(model=current_model)
    current_chat_id = await db.get_user_attribute(user_id, "current_chat_id")
    dialog_messages = await db.get_dialog_messages(user_id, current_chat_id)

    answer = await chatgpt_instance.send_message(
        message.text, dialog_messages, chat_mode=chat_mode
    )
    final = True
    if answer:
        answer = str(answer)[:4096]
    else:
        final = False
        answer = "Сообщение не может быть сгенерировано. Подождите или обратитесь в поддержку @trygptsupport."

    future.cancel()
    await bot.edit_message_text(
        chat_id=user_id, message_id=text.message_id, text=answer, parse_mode="MARKDOWN"
    )

    new_dialog_message = {"user": message.text, "bot": answer, "date": datetime.now()}

    try:
        await db.set_dialog_messages(
            user_id,
            await db.get_dialog_messages(user_id, dialog_id=None)
            + [new_dialog_message],
            dialog_id=None,
        )
    except TypeError:
        dialogue_id = await db.start_new_dialog(user_id, "Основной")
        await db.set_user_attribute(user_id, "current_dialog_id", dialogue_id)

    if not sub and final:
        await db.set_user_attribute(user_id, "available_prompts", prompts - 1)


async def is_subscriber_channel(user_id: int):
    user_channel_status = await bot.get_chat_member(
        chat_id=config.group_id, user_id=user_id
    )
    if user_channel_status.status == ChatMemberStatus.LEFT:
        return False
    return True


@router.callback_query(lambda q: q.data == "check_sub")
async def is_sub_channel(callback: CallbackQuery):
    user_channel_status = await bot.get_chat_member(
        chat_id=config.group_id, user_id=callback.from_user.id
    )
    if user_channel_status.status == ChatMemberStatus.LEFT:
        await bot.answer_callback_query(
            callback_query_id=callback.id,
            text="Чтобы использовать бота, необходимо быть подписанным на канал",
        )
    else:
        await callback.answer()
        await bot.edit_message_caption(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            caption=config.sub_true_message,
        )


async def change_dots(message_id, chat_id):
    num_dots = 0
    for i in range(
            100
    ):  # не ставлю бесконечный цикл, так после 1000 прохода ошибка (слишком частый редакт сообщения)
        message = f'Генерирую ответ{"." * num_dots}'
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=message
        )

        num_dots += 1
        if num_dots > 3:
            num_dots = 0

        await asyncio.sleep(1)


async def update_all_users_prompts():
    print("UPDATE PROMPTS")
    all_users = db.user_collection.find()
    all_users = await all_users.to_list(None)

    for user in all_users:
        new_prompts = 15

        await db.user_collection.update_one(
            {"chat_id": user["chat_id"]}, {"$set": {"available_prompts": new_prompts}}
        )


async def update_subs_users():
    print("UPDATE SUBS")
    all_users = db.user_collection.find()
    all_users = await all_users.to_list(None)

    for user in all_users:
        if user["to_subscribe_date"] < datetime.now():
            db.user_collection.update_one(
                {"chat_id": user["chat_id"]}, {"$set": {"subscriber": False}}
            )


async def check_payments():
    all_payments = db.payments_collection.find()

    async for payment in all_payments:
        chat_id = payment["user_id"]
        days = payment["days"]
        payment_id = payment["_id"]

        response = await payments.check_payment(payment_id)
        if response["status"] == "succeeded":
            await db.set_user_attribute(chat_id, "subscriber", True)
            a = await db.get_user_attribute(chat_id, "to_subscribe_date")
            if a and datetime.now() < a:
                await db.set_user_attribute(
                    chat_id, "to_subscribe_date", a + timedelta(days=days)
                )
            else:
                await db.set_user_attribute(
                    chat_id, "to_subscribe_date", datetime.now() + timedelta(days=days)
                )

            await db.payments_collection.delete_one({"_id": payment_id})
            await bot.send_message(chat_id=chat_id, text="Подписка успешно оформлена!")

        elif response["status"] == "cancelled":
            await db.payments_collection.delete_one({"_id": payment_id})


async def check_all_keys():
    api_keys_file = "configs/openAI_tokens.txt"
    working_keys_file = "configs/openAI_tokens.txt"
    non_working_keys_file = "configs/not_working.txt"

    api_keys = load_api_keys(api_keys_file)
    await check_and_write_keys(api_keys, working_keys_file, non_working_keys_file)


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_all_users_prompts, "interval", days=1)
    scheduler.add_job(update_subs_users, "interval", hours=3)
    scheduler.add_job(check_payments, "interval", seconds=20)
    scheduler.add_job(
        check_all_keys, "interval", days=1,
        start_date=datetime(2023, 11, 14, 21, 12)
    )

    print("Бот запущен!")
    logging.log(logging.DEBUG, msg="Бот запущен!!!")

    scheduler.start()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    openai.util.logger.setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)

    logging.basicConfig(filename="bot/logs/debug.lg", filemode="a", level=logging.DEBUG)

    asyncio.run(main())
