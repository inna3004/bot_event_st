import threading
from typing import Dict, Any, Optional, Union, List
import json
from storage.postgres_storage import PostgresStorage
import logging
import psycopg2
from psycopg2 import Error

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(handler)

db_lock = threading.Lock()


class BaseRepository:
    def __init__(self, storage: PostgresStorage):
        self.storage = storage
        self.local = threading.local()


class UsersRepository(BaseRepository):
    def create_user(self, contact: str, username: str, usersurname: str, region_id: int = None, step: int = 0,
                   age: int = None, gender: str = None, photo: str = None, geolocation: str = None,
                   is_admin: bool = False) -> Optional[int]:  # Теперь возвращаем ID пользователя
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """INSERT INTO users (contact, username, usersurname, region_id, registration_step, age, gender, 
                    photo, geolocation, is_admin) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id""",  # Добавляем RETURNING id
                    (contact, username, usersurname, region_id, step, age, gender, photo, geolocation, is_admin)
                )
                user_id = cursor.fetchone()[0]
                conn.commit()
                return user_id  # Возвращаем ID созданного пользователя
            except Exception as e:
                logger.error(f"Error creating user: {e}")
                conn.rollback()
                return None

    def get_user_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT * FROM users WHERE contact = %s",
                    (phone_number,)
                )
                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None
            except Exception as e:
                logger.error(f"Error getting user by phone: {e}")
                return None

    def set_user_step(self, user_id: int, step: int) -> bool:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """INSERT INTO users_states 
                    (user_id, current_step) 
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET current_step = EXCLUDED.current_step""",
                    (user_id, step)
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error setting user step: {e}")
                conn.rollback()
                return False

    def get_user_step(self, user_id: int) -> Dict[str, Any]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT current_step FROM users_states WHERE user_id = %s",
                    (user_id,)
                )
                result = cursor.fetchone()
                return {'current_step': result[0]} if result else {'current_step': 0}
            except Exception as e:
                logger.error(f"Error getting user step: {e}")
                return {'current_step': 0}

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT * FROM users WHERE contact = %s", (str(user_id),))
                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None
            except Exception as e:
                logger.error(f"Error getting user: {e}")
                return None

    def update_user(self, user_id: int, **kwargs) -> bool:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
                values = list(kwargs.values())
                values.append(str(user_id))

                cursor.execute(
                    f"UPDATE users SET {set_clause} WHERE contact = %s",
                    values
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error updating user: {e}")
                conn.rollback()
                return False


class TempDataRepository(BaseRepository):
    def save_temp_data(self, user_id: int, data: dict) -> bool:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                json_data = self._dumps(data)
                cursor.execute(
                    """INSERT INTO temp_user_data 
                    (user_id, json_data) 
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET json_data = EXCLUDED.json_data""",
                    (user_id, json_data)
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error saving temp data: {e}")
                conn.rollback()
                return False

    def get_temp_data(self, user_id: int) -> dict:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT json_data FROM temp_user_data WHERE user_id = %s",
                    (user_id,)
                )
                result = cursor.fetchone()
                if result and result[0]:
                    return self._loads(result[0])
                return {}
            except Exception as e:
                logger.error(f"Error getting temp data: {e}")
                return {}

    def clear_temp_data(self, user_id: int) -> bool:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "DELETE FROM temp_user_data WHERE user_id = %s",
                    (user_id,)
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error clearing temp data: {e}")
                conn.rollback()
                return False

    def _dumps(self, data: dict) -> str:
        try:
            return json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization error: {e}")
            return "{}"

    def _loads(self, json_str: str) -> dict:
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"JSON deserialization error: {e}")
            return {}


class RegionsRepository(BaseRepository):
    def get_all_regions(self) -> List[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, region as name FROM regions ORDER BY region")
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Error as e:
                logger.error(f"Ошибка получения списка регионов: {e}")
                return []

    def get_region_by_id(self, region_id: int) -> Optional[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT * FROM regions WHERE id = %s", (region_id,))
                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None
            except Error as e:
                logger.error(f"Ошибка получения региона {region_id}: {e}")
                return None

    def get_region_by_name(self, region_name: str) -> Optional[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, region as name FROM regions WHERE region = %s", (region_name,))
                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None
            except Error as e:
                logger.error(f"Ошибка получения региона по имени {region_name}: {e}")
                return None


class InterestsRepository(BaseRepository):
    def get_all_interests(self) -> List[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT id, interest as name 
                    FROM interests 
                    ORDER BY interest
                """)
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Error as e:
                logger.error(f"Ошибка получения списка интересов: {e}")
                return self._get_fallback_interests()

    def _get_fallback_interests(self):
        """Резервный список на случай проблем с БД"""
        return [
            {'id': 1, 'name': 'Волейбол'},
            {'id': 2, 'name': 'Футбол'},
            {'id': 3, 'name': 'Баскетбол'},
            {'id': 4, 'name': 'Теннис'},
            {'id': 5, 'name': 'Музыка'},
            {'id': 6, 'name': 'Игра на гитаре'},
            {'id': 7, 'name': 'Игра на пианино'},
            {'id': 8, 'name': 'Спорт'}
        ]

    def get_interest_by_name(self, interest_name: str) -> Optional[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                # Нормализуем имя для поиска
                normalized = self.normalize_interest_name(interest_name)
                cursor.execute("""
                    SELECT id, interest as name 
                    FROM interests 
                    WHERE LOWER(REPLACE(interest, 'ё', 'е')) = %s
                """, (normalized,))
                result = cursor.fetchone()
                if result:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, result))
                return None
            except Error as e:
                logger.error(f"Ошибка поиска интереса: {e}")
                return None

    @staticmethod
    def normalize_interest_name(name: str) -> str:
        """Приводим названия интересов к единому формату"""
        name = name.lower().strip()
        replacements = {
            'спорт': 'волейбол',  # Перенаправление категории на конкретный интерес
            'гитара': 'игра на гитаре',
            'пианино': 'игра на пианино'
        }
        return replacements.get(name, name)

    def find_similar_interests(self, search_term: str) -> List[Dict[str, Any]]:
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                search_term = f"%{search_term.lower()}%"
                cursor.execute("""
                    SELECT id, interest as name 
                    FROM interests 
                    WHERE LOWER(interest) LIKE %s
                    LIMIT 5
                """, (search_term,))
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except Error as e:
                logger.error(f"Ошибка поиска похожих интересов: {e}")
                return []

    def add_user_interest(self, user_id: int, interest_id: int) -> bool:
        """
        Добавляет связь пользователь-интерес
        :return: True если связь добавлена или уже существует
        """
        with self.storage.connection() as conn:
            cursor = conn.cursor()
            try:
                # Проверяем существование интереса
                cursor.execute("SELECT 1 FROM interests WHERE id = %s", (interest_id,))
                if not cursor.fetchone():
                    logger.error(f"Интерес {interest_id} не существует")
                    return False

                # Добавляем связь (игнорируем дубликаты)
                cursor.execute(
                    """INSERT INTO user_interests (user_id, interest_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, interest_id) DO NOTHING""",
                    (user_id, interest_id)
                )
                conn.commit()
                return cursor.rowcount > 0  # True если была добавлена новая связь
            except Exception as e:
                conn.rollback()
                logger.error(f"Ошибка добавления интереса {interest_id} для пользователя {user_id}: {e}")
                return False