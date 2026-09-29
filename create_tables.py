from DbConnector import DbConnector
from tabulate import tabulate


def create_trip_table(cursor):
    cursor.execute("""
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
    """)


def create_gps_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS GPSPoint (
            trip_record_id BIGINT NOT NULL,
            point_index INT NOT NULL,
            longitude DOUBLE NOT NULL,
            latitude DOUBLE NOT NULL,

            PRIMARY KEY (trip_record_id, point_index),

            FOREIGN KEY (trip_record_id)
                REFERENCES Trip(trip_record_id)
        ) ENGINE = InnoDB
    """)


def main():
    connection = DbConnector()
    cursor = connection.cursor

    try:
        # Trip must exist before GPSPoint because of the foreign key.
        create_trip_table(cursor)
        create_gps_table(cursor)

        cursor.execute("SHOW TABLES")
        print(tabulate(cursor.fetchall(), headers=cursor.column_names))

    finally:
        connection.close_connection()


if __name__ == "__main__":
    main()