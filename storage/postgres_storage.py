import django
import os
import psycopg2
from contextlib import contextmanager
from typing import Optional, Iterator
from telebot import logger

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')
django.setup()


class PostgresStorage:
    def __init__(self, dbname: str, user: str, password: str,
                 host: str = 'localhost', port: str = '5433'):
        """
        Инициализация подключения к PostgreSQL

        :param dbname: имя базы данных
        :param user: пользователь
        :param password: пароль
        :param host: хост (по умолчанию localhost)
        :param port: порт (по умолчанию 5433)
        """
        self.connection_params = {
            'dbname': dbname,
            'user': user,
            'password': password,
            'host': host,
            'port': port,
            'client_encoding': 'UTF8',  # Явное указание кодировки
            'connect_timeout': 5,  # Таймаут подключения 5 сек
        }
        self._check_encoding_support()

    def _check_encoding_support(self) -> None:
        """Проверяет поддержку UTF-8 на сервере PostgreSQL"""
        try:
            with self.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SHOW server_encoding;")
                    encoding = cursor.fetchone()[0]
                    if encoding.lower() != 'utf8':
                        logger.warning(
                            f"Сервер использует кодировку {encoding}. "
                            "Рекомендуется UTF8 для корректной работы с Unicode"
                        )
        except Exception as e:
            logger.error(f"Ошибка проверки кодировки сервера: {e}")
            raise

    @contextmanager
    def connection(self) -> Iterator[psycopg2.extensions.connection]:
        """
        Контекстный менеджер для работы с подключением к БД

        Пример использования:
        with storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.connection_params)
            # Устанавливаем уровень изоляции
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
            yield conn
        except psycopg2.OperationalError as e:
            logger.error(
                f"Ошибка подключения к БД {self.connection_params['dbname']}. "
                f"Параметры: {self._masked_params()}. Ошибка: {e}"
            )
            raise RuntimeError("Не удалось подключиться к базе данных") from e
        except psycopg2.Error as e:
            logger.error(f"Ошибка PostgreSQL: {e}")
            raise
        finally:
            if conn is not None and not conn.closed:
                conn.close()

    def _masked_params(self) -> dict:
        """Возвращает параметры подключения с маскированным паролем"""
        params = self.connection_params.copy()
        params['password'] = '***'
        return params

    def test_connection(self) -> bool:
        """Проверяет доступность базы данных"""
        try:
            with self.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return cursor.fetchone()[0] == 1
        except Exception:
            return False

    def close(self) -> None:
        """
        Закрывает все активные соединения и освобождает ресурсы.
        Рекомендуется вызывать при завершении работы приложения.
        """
        if hasattr(self, '_active_connections'):
            for conn in self._active_connections:
                try:
                    if not conn.closed:
                        conn.close()
                        logger.debug(f"Закрыто соединение: {conn}")
                except Exception as e:
                    logger.error(f"Ошибка при закрытии соединения: {e}")
            del self._active_connections
        logger.info("Все соединения с БД закрыты")

    def __enter__(self):
        """Поддержка контекстного менеджера на уровне класса"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое закрытие при выходе из контекста"""
        self.close()

    def check_russian_support(self):
        """Проверяет корректность хранения русских символов"""
        test_phrase = "Тест ЁёВолонтёрство"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT %s::text", (test_phrase,))
                result = cursor.fetchone()[0]
                if result != test_phrase:
                    raise ValueError(
                        f"Ошибка кодировки! Ожидалось: {test_phrase}, получено: {result}"
                    )


def migrate_to_utf8(self) -> bool:
    """
    Конвертирует текстовые данные в базе в корректную UTF-8 кодировку
    Возвращает True при успешной миграции

    Особенности:
    - Явное управление транзакциями
    - Подробное логирование
    - Гарантированное закрытие ресурсов
    - Обработка ошибок на всех уровнях
    """
    conn = None
    cursor = None
    migration_success = False

    try:
        # Устанавливаем соединение вне контекстного менеджера для полного контроля
        conn = psycopg2.connect(**self.connection_params)
        conn.autocommit = False  # Отключаем автокоммит для ручного управления
        cursor = conn.cursor()

        logger.info("Начало миграции данных в UTF-8...")

        # 1. Миграция для таблицы interests
        cursor.execute("""
            UPDATE interests 
            SET interest = convert_from(convert_to(interest, 'UTF8'), 'WIN1251')
            WHERE interest ~ '[^\\u0000-\\u007F]'
            RETURNING id  # Для логгирования измененных записей
        """)
        updated_rows = cursor.rowcount
        logger.info(f"Обновлено записей в interests: {updated_rows}")

        # 2. Добавьте аналогичные запросы для других таблиц при необходимости
        # cursor.execute("UPDATE users SET ...")

        # Фиксируем изменения
        conn.commit()
        migration_success = True
        logger.info("Миграция успешно завершена")

        return True

    except psycopg2.DatabaseError as db_error:
        logger.error(f"Ошибка базы данных при миграции: {db_error}")
        if conn:
            try:
                conn.rollback()
                logger.info("Транзакция откачена")
            except Exception as rollback_error:
                logger.error(f"Ошибка при откате транзакции: {rollback_error}")
        return False

    except Exception as unexpected_error:
        logger.error(f"Неожиданная ошибка при миграции: {unexpected_error}")
        return False

    finally:
        # Гарантированное освобождение ресурсов
        try:
            if cursor and not cursor.closed:
                cursor.close()
                logger.debug("Курсор закрыт")
        except Exception as cursor_error:
            logger.error(f"Ошибка при закрытии курсора: {cursor_error}")

        try:
            if conn and not conn.closed:
                conn.close()
                logger.debug("Соединение с БД закрыто")
        except Exception as conn_error:
            logger.error(f"Ошибка при закрытии соединения: {conn_error}")

        if migration_success:
            logger.info("Процесс миграции завершен успешно")
        else:
            logger.warning("Процесс миграции завершен с ошибками")