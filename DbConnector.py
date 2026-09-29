import os
import mysql.connector as mysql


class DbConnector:
    """Connect to MySQL and provide a cursor."""

    def __init__(
        self,
        HOST="localhost",
        DATABASE="tdt4225",
        USER="root",
        PASSWORD=None
    ):
        if PASSWORD is None:
            PASSWORD = os.environ["MYSQL_PASSWORD"]

        self.db_connection = mysql.connect(
            host=HOST,
            database=DATABASE,
            user=USER,
            password=PASSWORD,
            port=3306
        )
        self.cursor = self.db_connection.cursor()
        print(f"Connected to database: {DATABASE}")

    def close_connection(self):
        self.cursor.close()
        self.db_connection.close()
        print("Database connection closed.")