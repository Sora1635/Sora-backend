from threading import Thread
import os
from app import app
from bot import main as bot_main

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))

def run_bot():
    bot_main()

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    bot_thread = Thread(target=run_bot)
    flask_thread.start()
    bot_thread.start()