"""
locales.py — Barcha bot matnlari O'zbek va Rus tillarida.
"""
from __future__ import annotations

TEXTS: dict[str, dict[str, str]] = {
    "uz": {
        "choose_language": (
            "🌐 <b>Tilni tanlang</b>\n\n"
            "Botdan foydalanish uchun tilni tanlang:"
        ),
        "language_saved": "✅ Til saqlandi: <b>O'zbek tili</b> 🇺🇿",
        "subscribe_required": (
            "⚠️ <b>Botdan foydalanish uchun</b>\n"
            "quyidagi kanal/guruhlarga a'zo bo'ling:\n\n"
            "A'zo bo'lgach <b>✅ Tekshirish</b> tugmasini bosing."
        ),
        "still_not_subscribed": (
            "❌ Siz hali barcha kanal/guruhlarga a'zo emassiz.\n"
            "Iltimos, yuqoridagi barcha kanal/guruhlarga a'zo bo'ling."
        ),
        "now_subscribed": (
            "✅ <b>Rahmat! Siz barcha kanallarga a'zo bo'ldingiz.</b>\n\n"
            "Endi botdan foydalanishingiz mumkin 🎬\n"
            "Kino kodini yuboring va filmni oling!"
        ),
        "check_subscription_btn": "✅ Tekshirish",
        "welcome": (
            "🎬 <b>KinoBotga xush kelibsiz</b>, {name}!\n\n"
            "Men sizning shaxsiy kino omboringizman.\n"
            "<b>Kino kodini</b> yuboring — filmni darhol oling.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Qanday foydalanish:</b>\n"
            "  • Kino kodini yozing — masalan <code>5055</code>\n"
            "  • Filmni soniyalar ichida oling 🍿\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Kod bilmasangiz — administrator bilan bog'laning."
        ),
        "movie_not_found": (
            "❌ <b>Kino topilmadi.</b>\n\n"
            "Kod <code>{code}</code> bo'yicha hech narsa yo'q.\n"
            "Kodni tekshirib, qayta urinib ko'ring."
        ),
        "movie_caption": (
            "🎬 <b>{title}</b>\n\n"
            "📌 <b>Kod:</b> <code>{code}</code>\n\n"
            "<i>Kinoni zavq bilan tomosha qiling! 🍿</i>"
        ),
        "movie_caption_no_title": (
            "📌 <b>Kod:</b> <code>{code}</code>\n\n"
            "<i>Kinoni zavq bilan tomosha qiling! 🍿</i>"
        ),
        "movie_send_error": (
            "⚠️ <b>Filmni yuborishda xatolik.</b>\n\n"
            "Fayl serverdan o'chirilgan bo'lishi mumkin.\n"
            "Administrator bilan bog'laning. Kod: <code>{code}</code>"
        ),
    },
    "ru": {
        "choose_language": (
            "🌐 <b>Выберите язык</b>\n\n"
            "Выберите язык для использования бота:"
        ),
        "language_saved": "✅ Язык сохранён: <b>Русский</b> 🇷🇺",
        "subscribe_required": (
            "⚠️ <b>Для использования бота</b>\n"
            "подпишитесь на следующие каналы/группы:\n\n"
            "После подписки нажмите <b>✅ Проверить</b>."
        ),
        "still_not_subscribed": (
            "❌ Вы ещё не подписаны на все каналы/группы.\n"
            "Пожалуйста, подпишитесь на все каналы/группы выше."
        ),
        "now_subscribed": (
            "✅ <b>Спасибо! Вы подписались на все каналы.</b>\n\n"
            "Теперь вы можете пользоваться ботом 🎬\n"
            "Отправьте код фильма и получите его!"
        ),
        "check_subscription_btn": "✅ Проверить",
        "welcome": (
            "🎬 <b>Добро пожаловать в KinoBot</b>, {name}!\n\n"
            "Я ваш личный кинохранилище.\n"
            "Отправьте <b>код фильма</b> — получите его мгновенно.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Как пользоваться:</b>\n"
            "  • Введите код — например <code>5055</code>\n"
            "  • Получите фильм за секунды 🍿\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Не знаете код? Обратитесь к администратору."
        ),
        "movie_not_found": (
            "❌ <b>Фильм не найден.</b>\n\n"
            "Фильм с кодом <code>{code}</code> не существует.\n"
            "Проверьте код и попробуйте снова."
        ),
        "movie_caption": (
            "🎬 <b>{title}</b>\n\n"
            "📌 <b>Код:</b> <code>{code}</code>\n\n"
            "<i>Приятного просмотра! 🍿</i>"
        ),
        "movie_caption_no_title": (
            "📌 <b>Код:</b> <code>{code}</code>\n\n"
            "<i>Приятного просмотра! 🍿</i>"
        ),
        "movie_send_error": (
            "⚠️ <b>Ошибка при отправке фильма.</b>\n\n"
            "Файл возможно удалён с серверов.\n"
            "Обратитесь к администратору. Код: <code>{code}</code>"
        ),
    },
}


def t(lang: str | None, key: str, **kwargs: object) -> str:
    """Tarjima matnini qaytaradi. lang yo'q bo'lsa 'uz' ishlatiladi."""
    lang = lang if lang in TEXTS else "uz"
    text = TEXTS[lang].get(key) or TEXTS["uz"].get(key, key)
    return text.format(**kwargs) if kwargs else text
