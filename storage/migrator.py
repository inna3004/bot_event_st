from storage.postgres_storage import PostgresStorage


class Migrator:
    def __init__(self, storage: PostgresStorage):
        self.storage = storage

    def migrate(self):
        try:
            with self.storage.connection() as conn:
                cursor = conn.cursor()

                queries = [
                    """
                    CREATE TABLE IF NOT EXISTS interests (
                        id SERIAL PRIMARY KEY,
                        interest TEXT NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS regions (
                        id SERIAL PRIMARY KEY,
                        region TEXT NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        contact TEXT NOT NULL,
                        username TEXT NOT NULL,
                        usersurname TEXT NOT NULL,
                        gender TEXT,
                        age INTEGER,
                        region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
                        registration_step INTEGER,
                        photo TEXT,
                        geolocation TEXT,
                        is_admin BOOLEAN DEFAULT FALSE
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS users_states (
                        user_id BIGINT PRIMARY KEY,
                        current_step INTEGER NOT NULL,
                        temp_data TEXT
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS temp_user_data (
                        user_id BIGINT PRIMARY KEY,
                        json_data TEXT NOT NULL
                    )
                    """,
                    """
                    CREATE TABLE IF NOT EXISTS user_interests (
                        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        interest_id INTEGER NOT NULL REFERENCES interests(id) ON DELETE CASCADE,
                        PRIMARY KEY (user_id, interest_id)
                    )
                    """
                ]

                for query in queries:
                    cursor.execute(query)

                conn.commit()
                print("Миграция PostgreSQL выполнена успешно")

        except Exception as e:
            print(f"Произошла ошибка: {str(e).encode('utf-8', errors='replace').decode('utf-8')}")


if __name__ == "__main__":
    migrator = Migrator(PostgresStorage("postgres", "postgres", "5g", "localhost", "5433"))
    migrator.migrate()