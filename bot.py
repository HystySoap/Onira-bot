from flask import Flask
from threading import Thread
import asyncio
import os
import logging
import sqlite3
import datetime
 
import ephem
import google.generativeai as genai
 
from telegram import (
     Update, ReplyKeyboardMarkup,
     InlineKeyboardButton, InlineKeyboardMarkup,
     LabeledPrice
 )
from telegram.ext import (
     Application, CommandHandler, MessageHandler,
     CallbackQueryHandler, PreCheckoutQueryHandler,
     filters, ContextTypes
 )
 
 logging.basicConfig(level=logging.INFO)
 
 # ============================================================
 # 🌑 КЛЮЧИ
 # ============================================================
 TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
 GEMINI_KEY = os.environ["GEMINI_KEY"]
 genai.configure(api_key=GEMINI_KEY)
 GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
 
 # Оплата — дополнительная функция. Отсутствие платёжного токена не должно
 # останавливать весь бот (например, сразу после обновления старого деплоя).
 PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
 
 DB_PATH = "onira.db"
 FREE_DREAMS = 3                  # 🎁 бесплатных снов на старте
 REFERRAL_BONUS = 3               # 🎁 снов за каждого приглашённого друга
 SUPPORT_CONTACT = "@HystySoap"   # 🌿 поддержка
 
 # 🌿 Группа «До и После» — участники получают безлимит бесплатно
 GROUP_CHAT_ID = -1003528588311
 
 
 # ============================================================
 # 🌑 ТАРИФЫ
 # ============================================================
 TARIFFS = {
     "moon": {
         "title": "🌙 Лунный месяц",
         "price": 299,
         "days": 30,
         "desc": "Один оборот Луны рядом с ONIRA.\nБезлимитные толкования снов 30 дней.",
     },
     "three_moons": {
         "title": "🌖 Три луны",
         "price": 699,
         "days": 90,
         "desc": "Три лунных цикла глубокой работы.\nВыгоднее месячного пути.",
@@ -533,245 +537,333 @@ async def check_access(user_id, context):
     if u.get("free_left", 0) > 0:
         return True, "free"
     return False, None
 
 
 def no_access_text(user_id, bot_username):
     link = f"https://t.me/{bot_username}?start=ref{user_id}"
     return (
         "🌑 Твои бесплатные толкования закончились.\n\n"
         "Но путь не обрывается — есть две тропы:\n\n"
         f"🎁 Пригласи друга — за каждого получишь +{REFERRAL_BONUS} толкования.\n"
         f"Твоя ссылка:\n{link}\n\n"
         "✨ Или открой подписку — и толкуй сны без ограничений.\n\n"
         "Выбери свой путь под Луной:"
     )
 
 
 # ============================================================
 # 🌑 КОМАНДЫ
 # ============================================================
 async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
     user_id = update.effective_user.id
     is_new = not user_exists(user_id)
     get_user(user_id)  # создаём при первом визите
 
     # Поддерживаем и старые ссылки ref_123456, и новые ref123456.
     if is_new and context.args:
         arg = context.args[0]
         if arg.startswith("ref"):
             try:
                 inviter_id = int(arg[3:].lstrip("_"))
                 if process_referral(user_id, inviter_id):
                     try:
                         await context.bot.send_message(
                             inviter_id,
                             "🎁 Твой друг пришёл по твоей ссылке!\n\n"
                             f"🌙 Тебе начислено +{REFERRAL_BONUS} бесплатных толкования. ✨",
                         )
                     except Exception:
                         pass
             except (ValueError, IndexError):
                 pass
 
     chats.pop(user_id, None)
     await update.message.reply_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
 
 
 async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
     await update.message.reply_text(
         "🌙 Ты в главном меню. Выбери путь:",
         reply_markup=main_menu_keyboard(),
     )
 
 
 # ============================================================
 # 💳 ОПЛАТА
 # ============================================================
 async def send_invoice(chat_id, tariff_key, context):
     if not PROVIDER_TOKEN:
         logging.error("PROVIDER_TOKEN не задан: отправка счёта недоступна")
         await context.bot.send_message(
             chat_id=chat_id,
             text=(
                 "🌑 Сейчас оплата временно недоступна. "
                 f"Пожалуйста, напиши в поддержку: {SUPPORT_CONTACT}"
             ),
         )
         return
 
     t = TARIFFS[tariff_key]
     await context.bot.send_invoice(
         chat_id=chat_id,
         title=t["title"],
         description=t["desc"],
         payload=f"sub:{tariff_key}",
         provider_token=PROVIDER_TOKEN,
         currency="RUB",
         prices=[LabeledPrice(t["title"], t["price"] * 100)],

 
 async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
     query = update.pre_checkout_query
     if query.invoice_payload.startswith(("sub:", "tariff:")):
         await query.answer(ok=True)
     else:
         await query.answer(ok=False, error_message="Что-то пошло не так. Попробуй ещё раз 🌑")
 
 
 async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
     user_id = update.effective_user.id
     payload = update.message.successful_payment.invoice_payload
     tariff_key = payload.split(":", 1)[1]
     t = TARIFFS.get(tariff_key)
     if t is None:
         await update.message.reply_text(
             "🌑 Оплата прошла, но тариф не распознан. Напиши, пожалуйста, в поддержку."
         )
         return
 
     u = get_user(user_id)
     now = datetime.datetime.utcnow()
     current_until = parse_dt(u.get("subscription_until"))
     base = current_until if (current_until and current_until > now) else now
     new_until = base + datetime.timedelta(days=t["days"])
 
     update_user(
         user_id,
         subscription_until=new_until.isoformat(),
         tariff=t["title"],
         autopay=1,
     )
 
     await update.message.reply_text(
         "🌕 Оплата прошла. Путь открыт.\n\n"
         f"✨ Тариф: {t['title']}\n"
         f"📅 Подписка активна до: {new_until.strftime('%d.%m.%Y')}\n"
         "🔄 Автопродление: включено\n\n"
         "Теперь твои сны не имеют границ.\n"
         "Отменить автопродление можно в любой момент в личном кабинете —\n"
         "доступ сохранится до конца срока. 🌙",
         reply_markup=main_menu_keyboard(),        
     )
 
 
 # ============================================================
 # 🌙 КНОПКИ И НАВИГАЦИЯ
 # ============================================================
 async def show_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
     user_id = update.effective_user.id
     is_member = await is_group_member(user_id, context)
     await update.effective_message.reply_text(
         cabinet_text(user_id, is_member),
         reply_markup=cabinet_keyboard(user_id),
     )
 
 
 async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
     bot_username = (await context.bot.get_me()).username
     await update.effective_message.reply_text(
         referral_text(update.effective_user.id, bot_username),
     )
 
 
 async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
     """Обрабатывает все inline-кнопки бота."""
     query = update.callback_query
     await query.answer()
     data = query.data or ""
     user_id = update.effective_user.id
 
     if data.startswith("buy:"):
         tariff_key = data.split(":", 1)[1]
         if tariff_key not in TARIFFS:
             await query.message.reply_text("🌑 Этот путь пока недоступен.")
             return
         await send_invoice(query.message.chat_id, tariff_key, context)
     elif data == "open_tariffs":
         await query.message.reply_text(tariffs_text(), reply_markup=tariffs_keyboard())
     elif data == "tell_dream":
         await query.message.reply_text(
             "🌙 Я слушаю. Расскажи свой сон так, как помнишь его.",
             reply_markup=main_menu_keyboard(),
         )
     elif data == "back_menu":
         await query.message.reply_text(
             "🌙 Ты в главном меню. Выбери путь:",
             reply_markup=main_menu_keyboard(),
         )
     elif data == "cancel_sub":
         update_user(user_id, autopay=0)
         await query.message.reply_text(
             "🌙 Автопродление отключено. Доступ сохранится до конца оплаченного срока.",
             reply_markup=main_menu_keyboard(),
         )
     elif data == "resume_sub":
         update_user(user_id, autopay=1)
         await query.message.reply_text(
             "🔄 Автопродление снова включено.",
             reply_markup=main_menu_keyboard(),
         )
     else:
         logging.warning("Неизвестная callback-команда: %s", data)
         await query.message.reply_text("🌑 Не узнала эту кнопку. Открой меню ещё раз.")
 
 # ============================================================
 # 🌙 ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
 # ============================================================
 async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
     if update.effective_chat.type != "private":
         return
 
     user_id = update.effective_user.id
     text = update.message.text.strip()
     get_user(user_id)
 
     if text == "🌑 О ONIRA":
         await update.message.reply_text(ABOUT_TEXT, reply_markup=about_keyboard())
         return
 
     if text == "✨ Подписка":
         await update.message.reply_text(tariffs_text(), reply_markup=tariffs_keyboard())
         return
 
     if text == "❓ Помощь":
         await update.message.reply_text(HELP_TEXT, reply_markup=main_menu_keyboard())
         return
 
     if text == "🌙 Рассказать сон":
         await update.message.reply_text(
             "🌙 Я слушаю. Расскажи свой сон так, как помнишь его."
         )
         return
 
     if text == "👤 Личный кабинет":
         await show_cabinet(update, context)
         return
 
     if text == "🎁 Пригласить друга":
         await show_referral(update, context)
         return
 
     # ---------- ОБЫЧНОЕ СООБЩЕНИЕ = РАЗГОВОР С ONIRA ----------
     allowed, reason = await check_access(user_id, context)
     if not allowed:
         bot_username = (await context.bot.get_me()).username
         await update.message.reply_text(
             no_access_text(user_id, bot_username),
             reply_markup=tariffs_keyboard(),
         )
         return
 
     await update.message.chat.send_action("typing")
 
     try:
         if user_id not in chats:
             model = genai.GenerativeModel(
                 model_name=GEMINI_MODEL,
                 system_instruction=SYSTEM_PROMPT,
             )
             chats[user_id] = model.start_chat(history=[])
 
         # Синхронный SDK Gemini не должен блокировать обработку других апдейтов.
         response = await asyncio.to_thread(
             chats[user_id].send_message, text + moon_context()
         )
         answer = response.text
 
         # 🎁 Списываем бесплатный сон (только у тех, кто без подписки и не в группе)
         if reason == "free":
             u = get_user(user_id)
             new_free = max(0, u.get("free_left", 0) - 1)
             update_user(
                 user_id,
                 free_left=new_free,
                 dreams_count=u.get("dreams_count", 0) + 1,
             )
             if new_free == 1:
                 answer += "\n\n🌑 У тебя остался 1 бесплатный разговор со мной."
             elif new_free == 0:
                 answer += (
                     "\n\n🌑 Это был твой последний бесплатный разговор.\n"
                     "🎁 Пригласи друга — получишь ещё +3 толкования.\n"
                     "✨ Или открой подписку в меню — и границ не будет."
                 )
         else:
             u = get_user(user_id)
             update_user(user_id, dreams_count=u.get("dreams_count", 0) + 1)
 
         # Telegram не любит сообщения длиннее 4096 символов
         for i in range(0, len(answer), 4000):
             await update.message.reply_text(answer[i:i + 4000])
 
     except Exception:
         logging.exception("Gemini error")
         chats.pop(user_id, None)
         await update.message.reply_text(
             "🌑 Туман сгустился, и я на миг потеряла нить...\n"
             "Повтори, пожалуйста, ещё раз."
         )
 
 
 async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
     """Точка входа для обычных текстовых сообщений Telegram."""
     await handle_message(update, context)
 
 
 # ============================================================
 # 🌐 FLASK (чтобы хостинг не засыпал)
 # ============================================================
 app = Flask(__name__)
 
 
 @app.route("/")
 def home():
     return "ONIRA is dreaming... 🌙"
 
 
 def run_flask():
     app.run(host="0.0.0.0", port=8080)
 
 
 def register_handlers(application):
     """Register all Telegram handlers in a separately testable step."""
     application.add_handler(CommandHandler("start", start))
     application.add_handler(CommandHandler("menu", menu))
     application.add_handler(CallbackQueryHandler(handle_callback))
     application.add_handler(PreCheckoutQueryHandler(precheckout))
     application.add_handler(
         MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment)
     )
     application.add_handler(
         MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
     )
 
 
 # ============================================================
 # 🌕 ЗАПУСК
 # ============================================================
 def main():
     init_db()
 
     Thread(target=run_flask, daemon=True).start()
 
     application = Application.builder().token(TELEGRAM_TOKEN).build()
     register_handlers(application)
 
     logging.info("🌙 ONIRA пробудилась...")
     application.run_polling()
 
 
 if __name__ == "__main__":
     main()
