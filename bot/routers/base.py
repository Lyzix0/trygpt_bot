from datetime import datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

from database import Database
import configuration as config
from payments import Payments

db = Database()
payments = Payments(
    config.config_yaml["yoomoney_id"], config.config_yaml["yoomoney_token"], db
)
bot = Bot(config.config_yaml["telegram_token"], parse_mode=ParseMode.HTML)


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
