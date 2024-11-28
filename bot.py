from multiprocessing import Process, Manager, freeze_support

# Инициализация бота
API_TOKEN = "Вставьте ваш токен"  # Вставьте ваш токен Telegram API

import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from ozonscarper.main import get_products_links

bot = Bot(token=API_TOKEN)
router = Router()


# Подключение к базе данных
def get_db_connection():
    conn = sqlite3.connect("products.db")
    conn.row_factory = sqlite3.Row
    return conn


# Функция для создания таблицы (если её ещё нет)
def create_tables():
    with get_db_connection() as conn:
        # Таблица пользователей
        conn.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            telegram_id INTEGER UNIQUE NOT NULL
        )
        """)

        # Таблица отслеживаемых товаров
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ProductsToFollow (
            Follow_id INTEGER PRIMARY KEY AUTOINCREMENT,
            users_id INTEGER NOT NULL,
            product_query TEXT NOT NULL,
            cheapest_price_ever REAL,
            cheapest_prod_url TEXT,
            actual_lower_price REAL,
            FOREIGN KEY (users_id) REFERENCES Users (id)
        )
        """)
        conn.commit()


# Сохранение пользователя в базу данных
def save_user(telegram_id, username):
    with get_db_connection() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO Users (telegram_id, username)
        VALUES (?, ?)
        """, (telegram_id, username))
        conn.commit()


# Команда /start
@router.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Добро пожаловать! Используйте команду /find для поиска товаров.")


# Асинхронный поиск товаров через отдельный процесс
def process_search(item_name, chat_id, results_dict):
    try:
        # Выполняем поиск товаров
        products = get_products_links(item_name=item_name)
        results_dict[chat_id] = products
    except Exception as e:
        results_dict[chat_id] = {"error": str(e)}


# Команда /find
@router.message(Command("find"))
async def find_command(message: Message):
    await message.answer("Введите название товара для поиска:")

    @router.message(F.text)
    async def get_item_name(msg: Message):
        item_name = msg.text
        chat_id = msg.chat.id

        await msg.answer(f"Идёт поиск товара '{item_name}'...")

        # Запускаем процесс для поиска
        search_process = Process(target=process_search, args=(item_name, chat_id, TEMP_RESULTS))
        search_process.start()

        # Ожидаем завершения процесса поиска
        while search_process.is_alive():
            await asyncio.sleep(1)

        search_process.join()

        # Получаем результаты
        if chat_id not in TEMP_RESULTS:
            await msg.answer("Ошибка: результат поиска недоступен.")
            return

        products = TEMP_RESULTS[chat_id]
        if isinstance(products, dict) and "error" in products:
            await msg.answer(f"Ошибка при парсинге: {products['error']}")
            return

        if not products:
            await msg.answer("Товары не найдены.")
        else:
            for product in products:
                product_text = (
                    f"**Название**: {product['product_name']}\n"
                    f"**Цена с картой Ozon**: {product['product_ozon_card_price']}\n"
                    f"**Цена без карты**: {product['product_discount_price']}\n"
                    f"**Ссылка**: [Перейти]({product['url']})"
                )
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Отслеживать",
                                callback_data=f"track:{products.index(product)}",  # Передаём индекс
                            )
                        ]
                    ]
                )
                await msg.answer(product_text, reply_markup=keyboard, parse_mode="Markdown")


# Обработка нажатия кнопки "Отслеживать"
@router.callback_query(F.data.startswith("track:"))
async def track_product(callback: CallbackQuery):
    user_id = callback.message.chat.id
    product_index = int(callback.data.split(":")[1])  # Извлекаем индекс продукта

    # Сохраняем пользователя в базу
    save_user(telegram_id=user_id, username=callback.from_user.username or "Unknown")

    # Получаем пользователя из базы
    with get_db_connection() as conn:
        user_db = conn.execute("SELECT id FROM Users WHERE telegram_id = ?", (user_id,)).fetchone()

    if not user_db:
        await callback.answer("Ошибка: пользователь не найден в базе данных.")
        return

    user_db_id = user_db["id"]

    # Ищем товар во временном хранилище
    product = TEMP_RESULTS.get(user_id, [])[product_index]

    if product:
        with get_db_connection() as conn:
            # Проверяем, существует ли товар в таблице ProductsToFollow
            existing_product = conn.execute(
                """
                SELECT * FROM ProductsToFollow 
                WHERE users_id = ? AND product_query = ? AND cheapest_prod_url = ?
                """,
                (user_db_id, product["product_name"], product["url"])
            ).fetchone()

            if existing_product:
                # Если товар уже добавлен
                await callback.answer("Товар уже добавлен в отслеживаемые!", show_alert=True)
            else:
                # Если товар еще не добавлен
                conn.execute(
                    """
                    INSERT INTO ProductsToFollow (users_id, product_query, cheapest_price_ever, cheapest_prod_url, actual_lower_price)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_db_id,
                        product["product_name"],
                        product["product_ozon_card_price"],
                        product["url"],
                        product["product_discount_price"]
                    )
                )
                conn.commit()
                await callback.answer("Товар успешно добавлен в отслеживаемые!", show_alert=True)
    else:
        await callback.answer("Товар не найден или устарел.", show_alert=True)


# Команда /followed
@router.message(Command("followed"))
async def followed_command(message: Message):
    user_id = message.from_user.id

    # Извлекаем отслеживаемые товары из БД
    with get_db_connection() as conn:
        followed_products = conn.execute("""
            SELECT Follow_id, product_query, cheapest_price_ever, actual_lower_price, cheapest_prod_url
            FROM ProductsToFollow
            WHERE users_id = (
                SELECT id FROM Users WHERE telegram_id = ?
            )
        """, (user_id,)).fetchall()

    if not followed_products:
        await message.answer("Вы ещё не добавили товары в список отслеживаемых.")
        return

    for product in followed_products:
        product_text = (
            f"**Название**: {product['product_query']}\n"
            f"**Самая низкая цена**: {product['cheapest_price_ever']}₽\n"
            f"**Актуальная цена**: {product['actual_lower_price']}₽\n"
            f"**Ссылка**: [Перейти]({product['cheapest_prod_url']})"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Перестать отслеживать",
                        callback_data=f"unfollow:{product['Follow_id']}",
                    )
                ]
            ]
        )
        await message.answer(product_text, reply_markup=keyboard, parse_mode="Markdown")


# Обработка кнопки "Перестать отслеживать"
@router.callback_query(F.data.startswith("unfollow:"))
async def unfollow_product(callback: CallbackQuery):
    follow_id = callback.data.split(":")[1]

    # Удаляем товар из БД
    with get_db_connection() as conn:
        conn.execute("""
            DELETE FROM ProductsToFollow WHERE Follow_id = ?
        """, (follow_id,))
        conn.commit()

    await callback.answer("Товар успешно удалён из отслеживаемых.", show_alert=True)
    await callback.message.delete()



# Основная функция
async def main():
    create_tables()
    dp = Dispatcher()
    dp.include_router(router)

    try:
        print("Бот запущен. Нажмите Ctrl+C для остановки.")
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    freeze_support()  # Для корректной работы multiprocessing на Windows
    manager = Manager()
    TEMP_RESULTS = manager.dict()
    asyncio.run(main())
