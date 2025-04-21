from fastapi import FastAPI
import uvicorn
import threading

import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime, timedelta
from aiocryptopay import AioCryptoPay
from telethon import TelegramClient
from telethon.sessions import StringSession
import os

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8094350096:AAF_2dFYmMSxeB_F40dOX1e8XorhwbRAIyk"
CRYPTO_PAY_TOKEN = "365966:AA7XaVNkTXI4wvOoUWIvHRboNJp1Ktk7ab7"
API_ID = 28745328
API_HASH = "99b7d5e0faedd6ddae2ebb8d792a763c"
SESSION_STRING = "1ApWapzMBuzlg5kbC1qweYA5ZT3MSHLcQB5PioEv0svE5RXgmdYRJFOCucCd9Bes_iGkb7pjLsqroPbht67tP6AyluObcfvut7fGBCC__xcs3-2_AEFBC26QcPcCGr2X2NQ9dPIOD_n28NZiSDZq8OA8ICJn58UkFXvoWcW_M-OXRBQLni7cEMI5h90Oon5VcUHgevuI3mD_pOYaNCajgdR1iRejeaRRhmRHlwEqisJ5y7FTEslJYpHgTiX_QQSJspTc1FNb8-XHIwAsmnGko_ZmHFqogMQkEoxILSZUhw4ux7VM1D4loFgGElqk0hNY9Su4xHL4RsLkKZ5VKAj5kFs0KmfSqG9Y="
ADMIN_ID = 7942521984

# Инициализация
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
crypto = AioCryptoPay(CRYPTO_PAY_TOKEN)

# Временная база данных
users_db = {}
payments_db = {}
promocodes_db = {}

# Клавиатуры
def main_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💳 Оплатить подписку")],
        [KeyboardButton(text="🔍 Поиск")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="👑 Админка")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def profile_keyboard(has_sub):
    buttons = []
    if not has_sub:
        buttons.append([InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_sub")])
    buttons.append([InlineKeyboardButton(text="🎁 Активировать промокод", callback_data="activate_promo")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def subscription_plans_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 день | 1$", callback_data="sub_1"),
            InlineKeyboardButton(text="3 дня | 2$", callback_data="sub_3")
        ],
        [
            InlineKeyboardButton(text="7 дней | 5$", callback_data="sub_7"),
            InlineKeyboardButton(text="14 дней | 7$", callback_data="sub_14")
        ],
        [InlineKeyboardButton(text="30 дней | 9$", callback_data="sub_30")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

def payment_confirmation_keyboard(invoice_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Оплатить", url=f"https://t.me/CryptoBot?start={invoice_id}"),
            InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_{invoice_id}")
        ]
    ])

def search_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 По номеру", callback_data="search_phone")],
        [InlineKeyboardButton(text="👤 По юзернейму", callback_data="search_username")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Выдать подписку", callback_data="admin_give_sub")],
        [InlineKeyboardButton(text="❌ Забрать подписку", callback_data="admin_remove_sub")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ])

# Состояния
class UserStates(StatesGroup):
    waiting_phone = State()
    waiting_username = State()
    waiting_promo = State()
    admin_give_sub = State()
    admin_remove_sub = State()

# Основные хэндлеры
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users_db:
        users_db[user_id] = {
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "subscription": None,
            "is_admin": user_id == ADMIN_ID
        }
    
    await message.answer(
        "👋 Добро пожаловать в бота!",
        reply_markup=main_keyboard(user_id == ADMIN_ID)
    )

@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    user = users_db.get(message.from_user.id, {})
    
    sub_status = ("✅ Подписка до " + user["subscription"].strftime("%d.%m.%Y %H:%M")) \
        if user.get("subscription") and user["subscription"] > datetime.now() \
        else "❌ Нет подписки"
    
    text = (
        "👤 <b>Ваш профиль:</b>\n\n"
        f"🆔 <b>ID:</b> {message.from_user.id}\n"
        f"👤 <b>Имя:</b> {user.get('first_name', 'Не указано')}\n"
        f"📌 <b>Юзернейм:</b> @{user.get('username', 'Не указан')}\n"
        f"🔒 <b>Статус:</b> {sub_status}"
    )
    
    await message.answer(
        text,
        reply_markup=profile_keyboard(
            user.get("subscription") and user["subscription"] > datetime.now()
        ),
        parse_mode="HTML"
    )

@dp.message(F.text == "💳 Оплатить подписку")
async def buy_subscription(message: types.Message):
    await message.answer("💰 <b>Выберите тарифный план:</b>", 
                        reply_markup=subscription_plans_keyboard(),
                        parse_mode="HTML")

@dp.message(F.text == "🔍 Поиск")
async def search_menu(message: types.Message):
    user_id = message.from_user.id
    user = users_db.get(user_id, {})
    
    if not user.get("subscription") or user["subscription"] < datetime.now():
        await message.answer("❌ Для использования поиска нужна активная подписка!")
        return
    
    await message.answer("🔍 <b>Выберите тип поиска:</b>", 
                        reply_markup=search_keyboard(),
                        parse_mode="HTML")

@dp.message(F.text == "👑 Админка")
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 <b>Админ-панель:</b>", 
                           reply_markup=admin_keyboard(),
                           parse_mode="HTML")
    else:
        await message.answer("❌ Доступ запрещен!")

# Обработчики подписки
@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription(callback: CallbackQuery):
    days = int(callback.data.split("_")[1])
    prices = {1: 1, 3: 2, 7: 5, 14: 7, 30: 9}
    amount = prices.get(days, 1)
    
    await callback.answer()
    await callback.message.answer(
        f"Вы уверены, что хотите купить подписку на {days} дней за {amount}$?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{days}_{amount}"),
                InlineKeyboardButton(text="❌ Нет", callback_data="cancel")
            ]
        ])
    )

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_subscription(callback: CallbackQuery):
    _, days, amount = callback.data.split("_")
    days = int(days)
    amount = float(amount)
    
    try:
        invoice = await crypto.create_invoice(
            asset="USDT",
            amount=amount,
            description=f"Подписка на {days} дней"
        )
        
        pay_url = f"https://t.me/CryptoBot?start={invoice.invoice_id}"
        invoice_id = invoice.invoice_id
        
        payments_db[invoice_id] = {
            "user_id": callback.from_user.id,
            "days": days,
            "amount": amount,
            "paid": False
        }
        
        await callback.message.answer(
            f"💳 <b>Ваш счет на оплату подписки на {days} дней:</b>\n\n"
            f"<b>Сумма:</b> {amount}$\n"
            f"<b>Ссылка для оплаты:</b> {pay_url}\n\n"
            "После оплаты нажмите кнопку <b>'Проверить оплату'</b>",
            reply_markup=payment_confirmation_keyboard(invoice_id),
            parse_mode="HTML"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса: {e}")
        await callback.message.answer(
            "❌ <b>Ошибка при создании платежа</b>\n"
            f"<i>{str(e)}</i>",
            parse_mode="HTML"
        )

@dp.callback_query(F.data.startswith("check_"))
async def check_payment(callback: CallbackQuery):
    invoice_id = int(callback.data.split("_")[1])
    payment = payments_db.get(invoice_id)
    
    if not payment:
        await callback.answer("Платеж не найден", show_alert=True)
        return
    
    if payment["paid"]:
        await callback.answer("Подписка уже активирована", show_alert=True)
        return
    
    try:
        invoice = await crypto.get_invoices(invoice_ids=invoice_id)
        
        if invoice.status == 'paid':
            payments_db[invoice_id]["paid"] = True
            user_id = payment["user_id"]
            days = payment["days"]
            
            current_sub = users_db[user_id].get("subscription")
            if current_sub and current_sub > datetime.now():
                new_sub = current_sub + timedelta(days=days)
            else:
                new_sub = datetime.now() + timedelta(days=days)
            
            users_db[user_id]["subscription"] = new_sub
            
            await callback.message.answer(
                f"🎉 <b>Подписка активирована до {new_sub.strftime('%d.%m.%Y %H:%M')}!</b>",
                reply_markup=main_keyboard(users_db[user_id].get("is_admin", False)),
                parse_mode="HTML"
            )
            await callback.answer("✅ Оплата подтверждена", show_alert=True)
        else:
            await callback.answer("❌ Оплата не найдена", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при проверке платежа: {e}")
        await callback.answer("❌ Ошибка при проверке", show_alert=True)

# Поисковые функции
async def perform_search(user_id, query, search_type):
    try:
        async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
            # Обработка юзернейма
            if search_type == "username":
                query = query.lstrip('@')
                query = f"t.me/{query}"
            
            # Отправляем запрос
            await client.send_message("@EnergyGram_robot", query)
            
            # Ждем 5 секунд перед проверкой сообщений
            await asyncio.sleep(5)
            
            # Получаем последние 2 сообщения
            messages = await client.get_messages("@EnergyGram_robot", limit=2)
            
            if len(messages) >= 2:
                return messages[0].text  # Берем предпоследнее сообщение
            elif messages:
                return messages[0].text  # Если только одно сообщение
            else:
                return "❌ Результатов не найдено"
            
    except Exception as e:
        logger.error(f"Ошибка при поиске: {e}")
        return f"❌ Ошибка при поиске: {str(e)}"

@dp.callback_query(F.data == "search_phone")
async def search_phone_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "🔢 <b>Введите номер телефона для поиска:</b>\n\n"
        "<i>Формат: +79991234567 или 89991234567</i>",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_phone)
    await callback.answer()

@dp.message(UserStates.waiting_phone)
async def process_phone_search(message: types.Message, state: FSMContext):
    phone = ''.join(filter(str.isdigit, message.text.strip()))
    
    if not phone or len(phone) < 10:
        await message.answer("❌ <b>Некорректный номер телефона!</b>", parse_mode="HTML")
        return
    
    await message.answer(f"🔍 <b>Ищем информацию по номеру:</b> {phone}...", parse_mode="HTML")
    
    try:
        loading_msg = await message.answer("⏳ Ожидайте, идет поиск...")
        result = await perform_search(message.from_user.id, phone, "phone")
        await loading_msg.delete()
        await message.answer(result, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}", parse_mode="HTML")
    
    await state.clear()

@dp.callback_query(F.data == "search_username")
async def search_username_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👤 <b>Введите username для поиска:</b>\n\n"
        "<i>Можно с @ или без</i>",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.waiting_username)
    await callback.answer()

@dp.message(UserStates.waiting_username)
async def process_username_search(message: types.Message, state: FSMContext):
    username = message.text.strip()
    
    if not username:
        await message.answer("❌ <b>Некорректный username!</b>", parse_mode="HTML")
        return
    
    await message.answer(f"🔍 <b>Ищем информацию по юзернейму:</b> {username}...", parse_mode="HTML")
    
    try:
        loading_msg = await message.answer("⏳ Ожидайте, идет поиск...")
        result = await perform_search(message.from_user.id, username, "username")
        await loading_msg.delete()
        
        # Форматируем результат для лучшего отображения
        if "t.me/" in result:
            result = result.replace("t.me/", "@")
        await message.answer(result, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}", parse_mode="HTML")
    
    await state.clear()

# Админ функции
@dp.callback_query(F.data == "admin_give_sub")
async def admin_give_sub_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👑 <b>Введите ID пользователя и количество дней через пробел:</b>\n"
        "<i>Например: 1234567 30</i>",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.admin_give_sub)
    await callback.answer()

@dp.message(UserStates.admin_give_sub)
async def process_admin_give_sub(message: types.Message, state: FSMContext):
    try:
        user_id, days = map(int, message.text.split())
        if user_id in users_db:
            current_sub = users_db[user_id].get("subscription")
            
            if current_sub and current_sub > datetime.now():
                new_sub = current_sub + timedelta(days=days)
            else:
                new_sub = datetime.now() + timedelta(days=days)
            
            users_db[user_id]["subscription"] = new_sub
            await message.answer(
                f"✅ <b>Пользователю {user_id} выдана подписка на {days} дней</b>\n"
                f"<i>Действует до: {new_sub.strftime('%d.%m.%Y %H:%M')}</i>",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@dp.callback_query(F.data == "admin_remove_sub")
async def admin_remove_sub_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👑 <b>Введите ID пользователя для удаления подписки:</b>",
        parse_mode="HTML"
    )
    await state.set_state(UserStates.admin_remove_sub)
    await callback.answer()

@dp.message(UserStates.admin_remove_sub)
async def process_admin_remove_sub(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        if user_id in users_db:
            users_db[user_id]["subscription"] = None
            await message.answer(
                f"❌ <b>Подписка пользователя {user_id} удалена</b>",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    active_subs = sum(1 for user in users_db.values() if user.get("subscription") and user["subscription"] > datetime.now())
    total_users = len(users_db)
    
    await callback.message.answer(
        "📊 <b>Статистика:</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {total_users}\n"
        f"✅ <b>Активных подписок:</b> {active_subs}",
        parse_mode="HTML"
    )
    await callback.answer()

# Запуск бота
async def on_startup():
    try:
        await bot.send_message(ADMIN_ID, "🤖 <b>Бот успешно запущен!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")

async def on_shutdown():
    await bot.session.close()
    await crypto.close()

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "bot_is_alive"}

async def run_bot():
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=asyncio.run, args=(run_bot(),), daemon=True)
    bot_thread.start()
    
    # Запускаем HTTP-сервер (для Render)
    uvicorn.run(app, host="0.0.0.0", port=8000)
