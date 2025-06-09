from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import sqlite3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
CHANNEL = os.getenv('CHANNEL_USERNAME')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db():
    conn = sqlite3.connect('channels.db')
    conn.row_factory = sqlite3.Row
    return conn

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if context.args and context.args[0].startswith('verify_'):
        token = context.args[0][7:]
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM verification_tokens WHERE token = ? AND used = 0 AND created_at > ?', 
                      (token, (datetime.now() - timedelta(hours=24)).isoformat()))
            row = c.fetchone()
            if row:
                try:
                    member = await context.bot.get_chat_member(CHANNEL, user.id)
                    if member.status in ['member', 'administrator', 'creator']:
                        c.execute('UPDATE verification_tokens SET used = 1 WHERE token = ?', (token,))
                        c.execute('UPDATE users SET subscription_verified = 1, last_checked = ? WHERE id = ?', 
                                  (datetime.now().isoformat(), row['user_id']))
                        conn.commit()
                        await update.message.reply_text('Подписка подтверждена! Доступ к платформе открыт.')
                    else:
                        await update.message.reply_text('Подпишись на @piar163 и повтори!')
                except Exception as e:
                    logging.error(f"Error checking subscription: {str(e)}")
                    await update.message.reply_text('Ошибка проверки. Попробуй позже.')
            else:
                await update.message.reply_text('Неверный или истекший токен.')
    else:
        await update.message.reply_text('Используй /start verify_TOKEN для проверки подписки.')

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args or not context.args[0].startswith('@'):
        await update.message.reply_text('Укажи канал: /subscribe @channel')
        return
    
    channel_username = context.args[0]
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, subscription_verified FROM users WHERE telegram_username = ?', (user.username,))
        user_row = c.fetchone()
        if not user_row or not user_row['subscription_verified']:
            await update.message.reply_text('Подпишись на @piar163 для доступа!')
            return
        
        c.execute('SELECT COUNT(*) as count FROM subscription_logs WHERE user_id = ? AND date > ?', 
                  (user_row['id'], (datetime.now() - timedelta(days=1)).isoformat()))
        if c.fetchone()['count'] >= 1000:  # Упростим для прототипа
            await update.message.reply_text('Лимит подписок достигнут!')
            return
        
        c.execute('INSERT INTO channels (channel_username, user_id) VALUES (?, ?)', (channel_username, user_row['id']))
        c.execute('INSERT INTO subscription_logs (user_id, date, subscription_count) VALUES (?, ?, ?)',
                  (user_row['id'], datetime.now().isoformat(), 1))
        conn.commit()
    
    await update.message.reply_text(f'Подписка на {channel_username} добавлена!')

async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, telegram_username FROM users WHERE subscription_verified = 1')
        users = c.fetchall()
        for user in users:
            try:
                keyboard = [[InlineKeyboardButton("Подтвердить", callback_data=f"verify_{user['id']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=user['telegram_username'],
                    text='Подтверди подписку на @piar163, чтобы сохранить доступ!',
                    reply_markup=reply_markup
                )
            except Exception as e:
                logging.error(f"Error sending check to {user['telegram_username']}: {str(e)}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = int(query.data.split('_')[1])
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE id = ? AND telegram_username = ?', (user_id, user.username))
        if not c.fetchone():
            await query.edit_message_text('Неверный пользователь.')
            return
        
        try:
            member = await context.bot.get_chat_member(CHANNEL, user.id)
            if member.status in ['member', 'administrator', 'creator']:
                c.execute('UPDATE users SET subscription_verified = 1, last_checked = ? WHERE id = ?', 
                          (datetime.now().isoformat(), user_id))
                await query.edit_message_text('Подписка подтверждена! Доступ сохранен.')
            else:
                c.execute('UPDATE users SET subscription_verified = 0, access_revoked = 1 WHERE id = ?', (user_id))
                await query.edit_message_text('Ты отписался от @piar163. Подпишись снова!')
            conn.commit()
        except Exception as e:
            logging.error(f"Error verifying subscription: {str(e)}")
            await query.edit_message_text('Ошибка проверки. Попробуй позже.')

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CallbackQueryHandler(button, pattern='^verify_'))
    app.job_queue.run_repeating(check_subscriptions, interval=7*24*60*60)
    
    # Вебхуки
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv('PORT', 8080)),
        url_path=f"/bot/{TOKEN}",
        webhook_url=f"https://YOUR_RENDER_URL/bot/{TOKEN}"
    )

if __name__ == '__main__':
    main()