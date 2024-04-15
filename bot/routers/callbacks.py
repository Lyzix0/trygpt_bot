from datetime import datetime

from aiogram import Router
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import configuration as config
from .base import dialogue_button_creation, db, payments, get_user_info

router = Router(name=__name__)


@router.callback_query(lambda q: q.data == "profile")
async def profile_callback(callback: CallbackQuery):
    await db.register_user_if_not_exists(callback)
    user_info = await get_user_info(callback=callback)
    await callback.bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        text=user_info[0],
        parse_mode=ParseMode.HTML,
        reply_markup=user_info[1],
    )


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
    await callback.bot.edit_message_text(
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
        await callback.bot.edit_message_text(
            message_id=callback.message.message_id,
            chat_id=user,
            text=last_message,
            parse_mode="MARKDOWN",
        )
    else:
        await callback.bot.edit_message_text(
            message_id=callback.message.message_id,
            chat_id=user,
            text=config.chat_modes[chat_mode]["welcome_message"],
        )


@router.callback_query(lambda q: q.data.startswith("pay"))
async def proceed_payment(callback: CallbackQuery):
    await callback.answer()
    msg = await callback.bot.send_message(callback.from_user.id, "Создаем ссылку для оплаты...")

    data = callback.data.split("|")
    amount = int(data[2])

    pay_info = await payments.create_payment(callback.from_user.id, amount)
    pay_redirect = pay_info["confirmation"]["confirmation_url"]

    go_button = InlineKeyboardButton(text="Перейти в оплате", url=pay_redirect)
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[go_button]])

    await callback.bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=msg.message_id,
        text=f"""Сумма к оплате составляет {amount} рублей. Подписка автоматически зачислиться на ваш баланс.""",
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


@router.callback_query(lambda q: q.data.startswith("set_chat_mode"))
async def callback_select_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    chat_mode = callback.data.split("|")[1]
    await db.set_user_attribute(callback.from_user.id, "current_chat_mode", chat_mode)
    name = await db.get_user_attribute(callback.from_user.id, "name")
    await callback.bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        text=f"{config.chat_modes[chat_mode]['welcome_message']}",
        parse_mode=ParseMode.HTML,
    )
    await db.start_new_dialog(name=name, user_id=callback.from_user.id)
    await state.clear()


@router.callback_query(lambda q: q.data == "check_sub")
async def is_sub_channel(callback: CallbackQuery):
    user_channel_status = await callback.bot.get_chat_member(
        chat_id=config.group_id, user_id=callback.from_user.id
    )
    if user_channel_status.status == ChatMemberStatus.LEFT:
        await callback.bot.answer_callback_query(
            callback_query_id=callback.id,
            text="Чтобы использовать бота, необходимо быть подписанным на канал",
        )
    else:
        await callback.answer()
        await callback.bot.edit_message_caption(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            caption=config.sub_true_message,
        )
