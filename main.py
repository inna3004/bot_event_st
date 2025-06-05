import telebot
from settings import BOT_TOKEN
import logging
from telebot import types
from storage.postgres_storage import PostgresStorage
from service.repository import UsersRepository
from storage.migrator import Migrator
from service.repository import TempDataRepository, RegionsRepository, InterestsRepository
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=5)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

storage = PostgresStorage(
    dbname='postgres',
    user='postgres',
    password='5g',
    host='localhost',
    port='5433'
)
try:
    storage.check_russian_support()
except Exception as e:
    logger.error(f"Проблема с кодировкой БД: {e}")
    raise
migrator = Migrator(storage)
migrator.migrate()

user_repository = UsersRepository(storage)
temp_data_repository = TempDataRepository(storage)
regions_repository = RegionsRepository(storage)
interests_repository = InterestsRepository(storage)

ADMIN_PHONE_NUMBERS = ['79141518959']

REG_STEPS = {
    'name': 1,
    'surname': 2,
    'gender': 3,
    'age': 4,
    'region': 5,
    'interests': 6,
    'photo': 7,
    'location': 8,
    'compile': 9
}


def get_phone_button():
    keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    button = types.KeyboardButton(text="Отправить номер телефона", request_contact=True)
    keyboard.add(button)
    return keyboard


def get_gender_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.add(
        types.KeyboardButton("Мужской"),
        types.KeyboardButton("Женский"),
        types.KeyboardButton("Пропустить"),
        types.KeyboardButton("❌ Отменить регистрацию")
    )
    return keyboard


def get_cancel_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("❌ Отменить регистрацию"))
    return keyboard

def get_skip_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        types.KeyboardButton("Пропустить"),
        types.KeyboardButton("❌ Отменить регистрацию")
    )
    return keyboard


def save_user_data(user_id: int, **kwargs):
    """Обертка для сохранения данных пользователя"""
    user = user_repository.get_user(user_id)
    if user:
        user_repository.update_user(user_id, **kwargs)
    else:
        user_repository.create_user(
            contact=user_id,
            username=kwargs.get('name', ''),
            usersurname=kwargs.get('surname', '')
        )
        if len(kwargs) > 2:
            user_repository.update_user(user_id, **{
                k: v for k, v in kwargs.items()
                if k not in ['name', 'surname']
            })


@bot.message_handler(func=lambda message: message.text.lower() == 'старт')
def handle_text_start(message):
    start_registration(message)


@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    try:
        user_id = message.from_user.id
        temp_data_repository.clear_temp_data(user_id)
        user_repository.set_user_step(user_id, 0)

        bot.send_message(
            message.chat.id,
            "Регистрация отменена. Вы можете начать заново с помощью /start",
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /cancel: {e}")
        bot.reply_to(message, "Произошла ошибка при отмене регистрации.")


def check_cancel(message):
    if message.text and ("отменить" in message.text.lower() or message.text.strip() == '/cancel'):
        handle_cancel(message)
        return True
    return False


@bot.message_handler(commands=['start'])
def start_registration(message):
    try:
        # Добавляем кнопку "Старт" в самое начало
        start_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        start_btn = types.KeyboardButton("/start")
        start_markup.add(start_btn)
        intro_text = """Что может этот бот:
- поиск пары;
- поиск друзей;
- знакомства по интересам и геолокации."""

        launch_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        launch_btn = types.KeyboardButton("Запустить")
        launch_markup.add(launch_btn)

        bot.send_message(
            message.chat.id,
            intro_text,
            reply_markup=launch_markup
        )

        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            process_launch_step
        )

    except Exception as e:
        logger.error(f"Ошибка в start_registration: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def process_launch_step(message):
    try:
        if check_cancel(message):
            return

        if message.text == "Запустить":
            phone_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            phone_btn = types.KeyboardButton("Предоставить номер", request_contact=True)
            phone_markup.add(phone_btn)

            bot.send_message(
                message.chat.id,
                "Просим предоставить номер телефона:",
                reply_markup=phone_markup
            )

            bot.register_next_step_handler_by_chat_id(
                message.chat.id,
                process_phone_step
            )
        else:
            bot.send_message(
                message.chat.id,
                "Пожалуйста, нажмите кнопку 'Запустить'",
                reply_markup=types.ReplyKeyboardRemove()
            )
            start_registration(message)
    except Exception as e:
        logger.error(f"Ошибка в process_launch_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def process_phone_step(message):
    try:
        if check_cancel(message):
            return

        if message.contact:
            phone_number = message.contact.phone_number
            is_admin = phone_number in ADMIN_PHONE_NUMBERS

            user = user_repository.get_user_by_phone(phone_number)

            if user:
                bot.send_message(
                    message.chat.id,
                    "Добро пожаловать обратно!",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            else:
                temp_data = {
                    'phone': phone_number,
                    'is_admin': is_admin,
                    'interests': []
                }
                temp_data_repository.save_temp_data(
                    user_id=message.from_user.id,
                    data=temp_data
                )
                ask_for_name(message)
    except Exception as e:
        logger.error(f"Ошибка в process_phone_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_name(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите ваше имя:",
        reply_markup=get_cancel_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['name'])
    bot.register_next_step_handler(msg, process_name_step)


def process_name_step(message):
    try:
        if check_cancel(message):
            return

        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        temp_data['name'] = message.text
        temp_data_repository.save_temp_data(message.from_user.id, temp_data)

        ask_for_surname(message)
    except Exception as e:
        logger.error(f"Ошибка в process_name_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_surname(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите вашу фамилию:",
        reply_markup=get_cancel_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['surname'])
    bot.register_next_step_handler(msg, process_surname_step)


def process_surname_step(message):
    try:
        if check_cancel(message):
            return

        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        temp_data['surname'] = message.text
        temp_data_repository.save_temp_data(message.from_user.id, temp_data)

        ask_for_gender(message)
    except Exception as e:
        logger.error(f"Ошибка в process_surname_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_gender(message):
    msg = bot.send_message(
        message.chat.id,
        "Укажите ваш пол: ",
        reply_markup=get_gender_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['gender'])
    bot.register_next_step_handler(msg, process_gender_step)


def process_gender_step(message):
    try:
        if check_cancel(message):
            return

        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        if message.text.lower() in ['мужской', 'женский']:
            temp_data['gender'] = message.text
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)
            ask_for_age(message)
        elif message.text.lower() == 'пропустить':
            ask_for_age(message)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, выберите вариант из меню")
            ask_for_gender(message)
    except Exception as e:
        logger.error(f"Ошибка в process_gender_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_age(message):
    msg = bot.send_message(
        message.chat.id,
        "Введите ваш возраст:",
        reply_markup=get_cancel_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['age'])
    bot.register_next_step_handler(msg, process_age_step)


def process_age_step(message):
    try:
        if check_cancel(message):
            return

        if message.text.isdigit() and 12 <= int(message.text) <= 120:
            temp_data = temp_data_repository.get_temp_data(message.from_user.id)
            temp_data['age'] = int(message.text)
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)

            ask_for_region(message)
        else:
            bot.send_message(
                message.chat.id,
                "Пожалуйста, введите корректный возраст (12-120):",
                reply_markup=get_cancel_keyboard()
            )
            ask_for_age(message)
    except Exception as e:
        logger.error(f"Ошибка в process_age_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_region(message):
    try:
        regions = regions_repository.get_all_regions()

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for region in regions:
            keyboard.add(types.KeyboardButton(region['name']))
        keyboard.add(types.KeyboardButton("❌ Отменить регистрацию"))

        msg = bot.send_message(
            message.chat.id,
            "Пожалуйста, выберите ваш регион:",
            reply_markup=keyboard
        )
        user_repository.set_user_step(message.from_user.id, REG_STEPS['region'])
        bot.register_next_step_handler(msg, process_region_step)
    except Exception as e:
        logger.error(f"Ошибка при запросе региона: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def process_region_step(message):
    try:
        if check_cancel(message):
            return

        region = regions_repository.get_region_by_name(message.text)

        if region:
            temp_data = temp_data_repository.get_temp_data(message.from_user.id)
            temp_data['region_id'] = region['id']
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)

            ask_for_interests(message)
        else:
            bot.send_message(message.chat.id, "Регион не найден. Пожалуйста, выберите из списка.")
            ask_for_region(message)
    except Exception as e:
        logger.error(f"Ошибка при обработке региона: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def get_interests_keyboard():
    try:
        interests = interests_repository.get_all_interests()

        popular = ['Волейбол', 'Футбол', 'Теннис', 'Музыка', 'Игра на гитаре']
        other = [i for i in interests if i['name'] not in popular]

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

        for interest in popular:
            if any(i['name'] == interest for i in interests):
                keyboard.add(types.KeyboardButton(interest))

        for interest in sorted(other, key=lambda x: x['name']):
            keyboard.add(types.KeyboardButton(interest['name']))

        keyboard.add(types.KeyboardButton("Пропустить"))
        keyboard.add(types.KeyboardButton("❌ Отменить регистрацию"))
        return keyboard
    except Exception as e:
        logger.error(f"Error creating interests keyboard: {e}")
        return types.ReplyKeyboardRemove()


def ask_for_interests(message):
    try:
        msg = bot.send_message(
            message.chat.id,
            "Выберите ваши интересы:",
            reply_markup=get_interests_keyboard()
        )
        user_repository.set_user_step(message.from_user.id, REG_STEPS['interests'])
        bot.register_next_step_handler(msg, process_interests_step)
    except Exception as e:
        logger.error(f"Ошибка при запросе интересов: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def process_interests_step(message):
    try:
        if check_cancel(message):
            return

        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        if 'interests' not in temp_data:
            temp_data['interests'] = []

        if message.text == "Пропустить":
            ask_for_photo(message)
            return

        interest = interests_repository.get_interest_by_name(message.text)

        if not interest:
            similar = interests_repository.find_similar_interests(message.text)
            if similar:
                response = "Интерес не найден. Возможно вы имели в виду:\n"
                response += "\n".join(f"- {i['name']}" for i in similar[:3])
                bot.send_message(message.chat.id, response)
            else:
                bot.send_message(
                    message.chat.id,
                    "Пожалуйста, выберите интерес из предложенных кнопок",
                    reply_markup=get_interests_keyboard()
                )
            return ask_for_interests(message)

        if interest['id'] in temp_data['interests']:
            bot.send_message(
                message.chat.id,
                "Этот интерес уже выбран. Выберите другой или нажмите 'Пропустить'",
                reply_markup=get_interests_keyboard()
            )
            return ask_for_interests(message)

        temp_data['interests'].append(interest['id'])
        temp_data_repository.save_temp_data(message.from_user.id, temp_data)

        bot.send_message(
            message.chat.id,
            f"✅ Добавлен интерес: {interest['name']}\nВыбрано: {len(temp_data['interests'])}",
            reply_markup=get_interests_keyboard()
        )

        ask_for_interests(message)

    except Exception as e:
        logger.error(f"Ошибка в process_interests_step: {e}")
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Пожалуйста, выберите интерес снова",
            reply_markup=get_interests_keyboard()
        )
        ask_for_interests(message)


def ask_for_photo(message):
    msg = bot.send_message(
        message.chat.id,
        "Пожалуйста, отправьте ваше фото:",
        reply_markup=get_skip_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['photo'])
    bot.register_next_step_handler(msg, process_photo_step)


def process_photo_step(message):
    try:
        if check_cancel(message):
            return

        if message.text and message.text.lower() == "пропустить":
            ask_for_location(message)
            return

        if message.content_type == 'photo':
            temp_data = temp_data_repository.get_temp_data(message.from_user.id)
            temp_data['photo'] = message.photo[-1].file_id
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)
            ask_for_location(message)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото или нажмите 'Пропустить'.")
            ask_for_photo(message)
    except Exception as e:
        logger.error(f"Ошибка в process_photo_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_location(message):
    msg = bot.send_message(
        message.chat.id,
        "Укажите Ваше местоположение:",
        reply_markup=get_skip_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['location'])
    bot.register_next_step_handler(msg, process_location_step)


def process_location_step(message):
    try:
        if check_cancel(message):
            return

        if message.text and message.text.lower() == "пропустить":
            complete_registration(message)
            return

        if message.content_type == 'location':
            temp_data = temp_data_repository.get_temp_data(message.from_user.id)
            temp_data['geolocation'] = f"{message.location.latitude},{message.location.longitude}"
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)

        complete_registration(message)
    except Exception as e:
        logger.error(f"Ошибка в process_location_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def complete_registration(message):
    try:
        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        if not temp_data:
            raise Exception("Temp data not found")

        logger.info(f"Final interests before save: {temp_data.get('interests', [])}")

        user_id = user_repository.create_user(
            contact=temp_data['phone'],
            username=temp_data['name'],
            usersurname=temp_data['surname'],
            region_id=temp_data.get('region_id'),
            age=temp_data.get('age'),
            gender=temp_data.get('gender'),
            photo=temp_data.get('photo'),  # Может быть None, если пропущено
            geolocation=temp_data.get('geolocation'),  # Может быть None, если пропущено
            is_admin=temp_data.get('is_admin', False),
            step=0
        )

        if not user_id:
            raise Exception("Failed to create user")

        if 'interests' in temp_data and temp_data['interests']:
            for interest_id in temp_data['interests']:
                try:
                    success = interests_repository.add_user_interest(user_id, interest_id)
                    logger.info(f"Interest {interest_id} added: {success}")
                    if not success:
                        logger.error(f"Failed to add interest {interest_id}")
                except Exception as e:
                    logger.error(f"Error adding interest {interest_id}: {e}")

        temp_data_repository.clear_temp_data(message.from_user.id)

        bot.send_message(
            message.chat.id,
            f"Регистрация завершена! Выбрано интересов: {len(temp_data.get('interests', []))}",
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Error in complete_registration: {e}")
        bot.reply_to(
            message,
            "Ошибка при завершении регистрации. Пожалуйста, попробуйте снова."
        )

if __name__ == '__main__':
    try:
        logger.info("Starting bot...")
        bot.polling(none_stop=True, timeout=30)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        storage.close()
