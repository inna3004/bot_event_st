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
        types.KeyboardButton("Пропустить")
    )
    return keyboard


def get_cancel_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('/cancel'))
    return keyboard


def save_user_data(user_id: int, **kwargs):
    """Обертка для сохранения данных пользователя"""
    user = user_repository.get_user(user_id)
    if user:
        user_repository.update_user(user_id, **kwargs)
    else:
        # Создаем нового пользователя с минимальными данными
        user_repository.create_user(
            contact=user_id,
            username=kwargs.get('name', ''),
            usersurname=kwargs.get('surname', '')
        )
        # Обновляем остальные данные
        if len(kwargs) > 2:
            user_repository.update_user(user_id, **{
                k: v for k, v in kwargs.items()
                if k not in ['name', 'surname']
            })


@bot.message_handler(commands=['start'])
def start_registration(message):
    try:
        # 1. Вступительное сообщение
        intro_text = """Что может этот бот:
- Функция 1
- Функция 2
- Функция 3"""

        # 2. Кнопка "Запустить"
        launch_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        launch_btn = types.KeyboardButton("Запустить")
        launch_markup.add(launch_btn)

        # Отправляем сообщение с кнопкой
        bot.send_message(
            message.chat.id,
            intro_text,
            reply_markup=launch_markup
        )

        def handle_text(message):
            if message.text == "Запустить":
                process_launch_step(message)
            else:
                bot.send_message(message.chat.id, "Пожалуйста, используйте кнопки меню")

        # Регистрируем обработчик для следующего сообщения
        bot.register_next_step_handler_by_chat_id(
            message.chat.id,
            process_launch_step
        )

    except Exception as e:
        logger.error(f"Ошибка в start_registration: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def process_launch_step(message):
    try:
        if message.text == "Запустить":
            # 3. Запрос номера телефона
            phone_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            phone_btn = types.KeyboardButton("Предоставить номер", request_contact=True)
            phone_markup.add(phone_btn)

            # Отправляем запрос номера
            bot.send_message(
                message.chat.id,
                "Просим предоставить номер телефона:",
                reply_markup=phone_markup
            )

            # Регистрируем обработчик для номера телефона
            bot.register_next_step_handler_by_chat_id(
                message.chat.id,
                process_phone_step
            )
        else:
            # Если получено неожиданное сообщение
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
                # Явно сохраняем is_admin
                temp_data = {
                    'phone': phone_number,
                    'is_admin': is_admin,  # Это должно сохраниться
                    'interests': []
                }
                temp_data_repository.save_temp_data(
                    user_id=message.from_user.id,
                    data=temp_data
                )
                ask_for_name(message)
    except Exception as e:  # Добавлен недостающий блок except
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
        # Сохраняем имя во временные данные
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
        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        temp_data['surname'] = message.text
        temp_data_repository.save_temp_data(message.from_user.id, temp_data)

        ask_for_gender(message)  # Добавляем запрос пола перед регионом
    except Exception as e:
        logger.error(f"Ошибка в process_surname_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_gender(message):
    msg = bot.send_message(
        message.chat.id,
        "Укажите ваш пол:",
        reply_markup=get_gender_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['gender'])
    bot.register_next_step_handler(msg, process_gender_step)


def process_gender_step(message):
    try:
        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        if message.text.lower() in ['мужской', 'женский']:
            temp_data['gender'] = message.text
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)
            ask_for_age(message)  # После пола запрашиваем возраст
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
        "Введите ваш возраст (12-120):",
        reply_markup=get_cancel_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['age'])
    bot.register_next_step_handler(msg, process_age_step)


def process_age_step(message):
    try:
        if message.text.isdigit() and 12 <= int(message.text) <= 120:
            # Сохраняем возраст во временные данные
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
            ask_for_region(message)
    except Exception as e:
        logger.error(f"Ошибка в process_region_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_region(message):
    try:
        # Получаем список регионов из базы
        regions = regions_repository.get_all_regions()

        # Создаем клавиатуру с регионами
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for region in regions:
            keyboard.add(types.KeyboardButton(region['name']))

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
        # Находим выбранный регион в базе
        region = regions_repository.get_region_by_name(message.text)

        if region:
            # Сохраняем region_id во временные данные
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


def ask_for_interests(message):
    try:
        msg = bot.send_message(
            message.chat.id,
            "Выберите ваши интересы (можно несколько, отправляйте по одному):",
            reply_markup=get_interests_keyboard()
        )
        user_repository.set_user_step(message.from_user.id, REG_STEPS['interests'])
        bot.register_next_step_handler(msg, process_interests_step)
    except Exception as e:
        logger.error(f"Ошибка при запросе интересов: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def get_interests_keyboard():
    try:
        interests = interests_repository.get_all_interests()

        # Сортируем по популярности (можно адаптировать)
        popular = ['Волейбол', 'Футбол', 'Теннис', 'Музыка', 'Игра на гитаре']
        other = [i for i in interests if i['name'] not in popular]

        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

        # Добавляем популярные первые
        for interest in popular:
            if any(i['name'] == interest for i in interests):
                keyboard.add(types.KeyboardButton(interest))

        # Затем остальные
        for interest in sorted(other, key=lambda x: x['name']):
            keyboard.add(types.KeyboardButton(interest['name']))

        keyboard.add(types.KeyboardButton("Пропустить"))
        return keyboard
    except Exception as e:
        logger.error(f"Error creating interests keyboard: {e}")
        return types.ReplyKeyboardRemove()


def process_interests_step(message):
    try:
        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        if 'interests' not in temp_data:
            temp_data['interests'] = []

        if message.text == "Пропустить":
            ask_for_photo(message)
            return

        # Нормализуем ввод пользователя
        interest = interests_repository.get_interest_by_name(message.text)

        if not interest:
            # Попробуем найти похожие интересы
            similar = self.find_similar_interests(message.text)
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

        # Проверяем дубликаты
        if interest['id'] in temp_data['interests']:
            bot.send_message(
                message.chat.id,
                "Этот интерес уже выбран. Выберите другой или нажмите 'Пропустить'",
                reply_markup=get_interests_keyboard()
            )
            return ask_for_interests(message)

        # Добавляем интерес
        temp_data['interests'].append(interest['id'])
        temp_data_repository.save_temp_data(message.from_user.id, temp_data)

        # Обновляем клавиатуру (убираем выбранные интересы)
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
        reply_markup=get_cancel_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['photo'])
    bot.register_next_step_handler(msg, process_photo_step)


def process_photo_step(message):
    try:
        if message.content_type == 'photo':
            temp_data = temp_data_repository.get_temp_data(message.from_user.id)
            temp_data['photo'] = message.photo[-1].file_id
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)
            ask_for_location(message)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте фото.")
            ask_for_photo(message)
    except Exception as e:
        logger.error(f"Ошибка в process_photo_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")

        interest = interests_repository.get_interest_by_name(message.text)

        if interest:
            if 'interests' not in temp_data:
                temp_data['interests'] = []

            if interest['id'] not in temp_data['interests']:
                temp_data['interests'].append(interest['id'])
                temp_data_repository.save_temp_data(message.from_user.id, temp_data)

            # Продолжаем выбор интересов
            ask_for_interests(message)
        else:
            bot.send_message(message.chat.id, "Интерес не найден. Пожалуйста, выберите из списка.")
            ask_for_interests(message)
    except Exception as e:
        logger.error(f"Ошибка при обработке интересов: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def ask_for_location(message):
    msg = bot.send_message(
        message.chat.id,
        "Укажите Ваше местоположение:",
        reply_markup=get_cancel_keyboard()
    )
    user_repository.set_user_step(message.from_user.id, REG_STEPS['location'])
    bot.register_next_step_handler(msg, process_location_step)  # Было process_surname_step


def process_location_step(message):
    try:
        if message.content_type == 'location':
            # Сохраняем геолокацию во временные данные
            temp_data = temp_data_repository.get_temp_data(message.from_user.id)
            temp_data['geolocation'] = f"{message.location.latitude},{message.location.longitude}"
            temp_data_repository.save_temp_data(message.from_user.id, temp_data)

            complete_registration(message)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте вашу локацию.")
            ask_for_location(message)
    except Exception as e:
        logger.error(f"Ошибка в process_location_step: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте позже.")


def complete_registration(message):
    try:
        temp_data = temp_data_repository.get_temp_data(message.from_user.id)
        if not temp_data:
            raise Exception("Temp data not found")

        # Логируем ВСЕ выбранные интересы
        logger.info(f"Final interests before save: {temp_data.get('interests', [])}")

        # Создаём пользователя
        user_id = user_repository.create_user(
            contact=temp_data['phone'],
            username=temp_data['name'],
            usersurname=temp_data['surname'],
            region_id=temp_data.get('region_id'),
            age=temp_data.get('age'),
            gender=temp_data.get('gender'),
            photo=temp_data.get('photo'),
            geolocation=temp_data.get('geolocation'),
            is_admin=temp_data.get('is_admin', False),
            step=0
        )

        if not user_id:
            raise Exception("Failed to create user")

        # Добавляем ВСЕ выбранные интересы
        if 'interests' in temp_data and temp_data['interests']:
            for interest_id in temp_data['interests']:
                try:
                    success = interests_repository.add_user_interest(user_id, interest_id)
                    logger.info(f"Interest {interest_id} added: {success}")
                    if not success:
                        logger.error(f"Failed to add interest {interest_id}")
                except Exception as e:
                    logger.error(f"Error adding interest {interest_id}: {e}")

        # Проверяем результат в БД
        with storage.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT interest_id FROM user_interests WHERE user_id = %s",
                (user_id,)
            )
            saved = cursor.fetchall()
            logger.info(f"Проверка БД: сохранено {len(saved)} интересов: {saved}")

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


@bot.message_handler(content_types=['text'])
def handle_registration(message):
    user_id = message.from_user.id
    user_data = user_repository.get_user(user_id)
    user_step = user_repository.get_user_step(user_id)

    if not user_data or not user_step:
        bot.send_message(message.chat.id, "Пожалуйста, начните регистрацию с помощью /start")
        return

    current_step = user_step.get('current_step', 0)

    try:
        if current_step == REG_STEPS['name']:
            save_user_data(user_id, name=message.text, current_step=REG_STEPS['surname'])
            bot.send_message(
                message.chat.id,
                f"Приятно познакомиться, {message.text}! Теперь введите вашу фамилию:",
                reply_markup=get_cancel_keyboard()
            )

        elif current_step == REG_STEPS['surname']:
            save_user_data(user_id, surname=message.text, current_step=REG_STEPS['gender'])
            bot.send_message(
                message.chat.id,
                "Укажите ваш пол:",
                reply_markup=get_gender_keyboard()
            )

        elif current_step == REG_STEPS['gender']:
            if message.text.lower() in ['мужской', 'женский']:
                save_user_data(user_id, gender=message.text, current_step=REG_STEPS['age'])
                bot.send_message(
                    message.chat.id,
                    "Введите ваш возраст:",
                    reply_markup=get_cancel_keyboard()
                )
            elif message.text.lower() == 'пропустить':
                save_user_data(user_id, gender=None, current_step=REG_STEPS['age'])
                bot.send_message(
                    message.chat.id,
                    "Введите ваш возраст:",
                    reply_markup=get_cancel_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Пожалуйста, выберите пол из предложенных вариантов или нажмите 'Пропустить'",
                    reply_markup=get_gender_keyboard()
                )

        elif current_step == REG_STEPS['age']:
            if message.text.isdigit() and 12 <= int(message.text) <= 120:
                save_user_data(user_id, age=int(message.text), current_step=REG_STEPS['region'])
                bot.send_message(
                    message.chat.id,
                    "Укажите ваш регион:",
                    reply_markup=get_cancel_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "Пожалуйста, введите корректный возраст (1-120):",
                    reply_markup=get_cancel_keyboard()
                )

        elif current_step == REG_STEPS['region']:
            save_user_data(user_id, region=message.text, current_step=REG_STEPS['interests'])
            bot.send_message(
                message.chat.id,
                "Укажите ваши интересы :",
                reply_markup=get_cancel_keyboard()
            )

        elif current_step == REG_STEPS['interests']:
            save_user_data(user_id, interests=message.text, current_step=REG_STEPS['photo'])
            bot.send_message(
                message.chat.id,
                "Отправьте ваше фото:",
                reply_markup=get_cancel_keyboard()
            )

    except Exception as e:
        logger.error(f"Ошибка в обработке сообщения: {e}")
        bot.reply_to(message, "Произошла ошибка. Пожалуйста, попробуйте снова.")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    user_data = user_repository.get_user(user_id)
    user_step = user_repository.get_user_step(user_id)

    if user_data and user_step.get('current_step') == REG_STEPS['photo']:
        try:
            photo_id = message.photo[-1].file_id
            save_user_data(user_id, photo=photo_id, current_step=REG_STEPS['location'])
            bot.send_message(
                message.chat.id,
                "Теперь отправьте вашу локацию:",
                reply_markup=types.ReplyKeyboardMarkup(
                    [[types.KeyboardButton("Отправить локацию", request_location=True)]],
                    resize_keyboard=True
                )
            )
        except Exception as e:
            logger.error(f"Ошибка обработки фото: {e}")
            bot.reply_to(message, "Не удалось обработать фото. Попробуйте еще раз.")


@bot.message_handler(content_types=['location'])
def handle_location(message):
    user_id = message.from_user.id
    user_data = user_repository.get_user(user_id)
    user_step = user_repository.get_user_step(user_id)

    if user_data and user_step.get('current_step') == REG_STEPS['location']:
        try:
            latitude = message.location.latitude
            longitude = message.location.longitude
            save_user_data(
                user_id,
                geolocation=f"{latitude},{longitude}",
                current_step=None
            )
            bot.send_message(
                message.chat.id,
                "Регистрация успешно завершена! Спасибо!",
                reply_markup=types.ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Ошибка обработки локации: {e}")
            bot.reply_to(message, "Не удалось обработать локацию. Попробуйте еще раз.")


if __name__ == '__main__':
    try:
        logger.info("Starting bot...")
        bot.polling(none_stop=True, timeout=30)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
    finally:
        storage.close()
