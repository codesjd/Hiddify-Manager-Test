import threading
import time

from apiflask import abort
from flask import request
from flask_restful import Resource
from werkzeug.local import LocalProxy

from hiddifypanel import Events
from hiddifypanel.cache import cache
from hiddifypanel.models import *

_bot = None
# Guards both _bot's lazy construction and every place that mutates the
# shared bot's .token/.username or calls into it - uwsgi runs this app with
# enable-threads, so a settings save (register_bot/init_app, reassigning
# .token mid-flight) and an incoming webhook (TGBotResource.post, reading
# .token via process_new_updates) can now genuinely interleave on the same
# TeleBot instance. Without this, an update in flight during a token change
# could get processed against a half-updated bot.
_bot_lock = threading.RLock()


def _get_bot():
    global _bot
    with _bot_lock:
        if _bot is None:
            import telebot

            class ExceptionHandler(telebot.ExceptionHandler):
                def handle(self, exception):
                    error_msg = str(exception)
                    telebot.logger.error(f"Telegram bot error: {error_msg}")
                    try:
                        if "webhook" in error_msg.lower():
                            if hasattr(_bot, "remove_webhook"):
                                _bot.remove_webhook()
                                telebot.logger.info("Removed webhook due to error")
                        elif "connection" in error_msg.lower():
                            import time

                            time.sleep(5)
                            return True
                    except Exception as e:
                        telebot.logger.error(f"Error during recovery attempt: {str(e)}")
                    return False

            _bot = telebot.TeleBot("1:2", parse_mode="HTML", threaded=False, exception_handler=ExceptionHandler())
            _bot.username = ""
        return _bot


bot = LocalProxy(_get_bot)


@cache.cache(1000)
def register_bot_cached(set_hook=False, remove_hook=False):
    return register_bot(set_hook, remove_hook)


def register_bot(set_hook=False, remove_hook=False):
    try:
        with _bot_lock:
            token = hconfig(ConfigEnum.telegram_bot_token)
            if token:
                bot.token = hconfig(ConfigEnum.telegram_bot_token)
                try:
                    bot.username = bot.get_me().username
                except BaseException:
                    pass
                if remove_hook:
                    bot.remove_webhook()
                domain = Domain.get_panel_link()
                if not domain:
                    raise Exception("Cannot get valid domain for setting telegram bot webhook")

                admin_proxy_path = hconfig(ConfigEnum.proxy_path_admin)

                user_secret = AdminUser.get_super_admin_uuid()
                if set_hook:
                    bot.set_webhook(url=f"https://{domain}/{admin_proxy_path}/{user_secret}/api/v1/tgbot/")
    except Exception as e:
        import telebot

        telebot.logger.error(e)


def init_app(app):
    with app.app_context():
        with _bot_lock:
            token = hconfig(ConfigEnum.telegram_bot_token)
            if token:
                bot.token = token
                try:
                    bot.username = bot.get_me().username
                except BaseException:
                    pass


class TGBotResource(Resource):
    def post(self):
        try:
            if request.headers.get("content-type") == "application/json":
                json_string = request.get_data().decode("utf-8")
                import telebot

                update = telebot.types.Update.de_json(json_string)
                with _bot_lock:
                    bot.process_new_updates([update])
                return ""
            else:
                abort(403)
        except Exception as e:
            print("Error", e)
            import traceback

            traceback.print_exc()
            return "", 500
