
from DbConnector import DbConnector
from tabulate import tabulate


class CreateTables:

    def __init__(self):
        self.connection = DbConnector()
        self.db_connection = self.connection.db_connection
        self.cursor = self.connection.cursor

    def create_trip_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS Trip (
            trip_record_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            trip_id VARCHAR(25) NOT NULL,
            taxi_id VARCHAR(20) NOT NULL,
            call_type CHAR(1),
            origin_call INT,
            origin_stand INT,
            start_timestamp BIGINT NOT NULL,
            day_type CHAR(1),
            missing_data BOOLEAN NOT NULL,
            num_points INT NOT NULL,
            duplicate_id BOOLEAN NOT NULL DEFAULT FALSE,

            INDEX idx_trip_id (trip_id),
            INDEX idx_taxi_start (taxi_id, start_timestamp),
            INDEX idx_call_type (call_type)
        ) ENGINE = InnoDB
        """

        self.cursor.execute(query)
        self.db_connection.commit()
        print("Trip table created.")

    def create_gps_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS GPSPoint (
            trip_record_id BIGINT NOT NULL,
            point_index INT NOT NULL,
            longitude DOUBLE NOT NULL,
            latitude DOUBLE NOT NULL,

            PRIMARY KEY (trip_record_id, point_index),

            FOREIGN KEY (trip_record_id)
                REFERENCES Trip(trip_record_id)
        ) ENGINE = InnoDB
        """

        self.cursor.execute(query)
        self.db_connection.commit()
        print("GPSPoint table created.")

    def show_tables(self):
        self.cursor.execute("SHOW TABLES")
        rows = self.cursor.fetchall()
        print(tabulate(rows, headers=self.cursor.column_names))


def main():
    program = None

    try:
        program = CreateTables()

        # Create Trip first because GPSPoint refers to it.
        program.create_trip_table()
        program.create_gps_table()

        # Verify that the tables exist.
        program.show_tables()

    except Exception as e:
        print("ERROR:", e)

    finally:
        if program:
            program.connection.close_connection()


if __name__ == "__main__":
    main()