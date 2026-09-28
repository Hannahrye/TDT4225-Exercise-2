
from DbConnector import DbConnector
import time

connection = DbConnector()
cursor = connection.cursor

BATCH_SIZE = 5000

try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS TripDistance (
            trip_record_id BIGINT PRIMARY KEY,
            distance_km DOUBLE NOT NULL,
            FOREIGN KEY (trip_record_id)
                REFERENCES Trip(trip_record_id)
        ) ENGINE=InnoDB
    """)
    connection.db_connection.commit()

    # Resume after the last completed trip.
    # This assumes batches are processed in ID order.
    cursor.execute("""
        SELECT COALESCE(MAX(trip_record_id), 0)
        FROM TripDistance
    """)
    last_id = cursor.fetchone()[0]

    cursor.execute("""
        SELECT MAX(trip_record_id)
        FROM Trip
    """)
    max_id = cursor.fetchone()[0]

    start_time = time.time()

    while last_id < max_id:
        cursor.execute("""
            SELECT trip_record_id
            FROM Trip
            WHERE trip_record_id > %s
            ORDER BY trip_record_id
            LIMIT %s
        """, (last_id, BATCH_SIZE))

        ids = [row[0] for row in cursor.fetchall()]

        if not ids:
            break

        batch_end = ids[-1]

        # Include every trip, including trips with 0 or 1 GPS point.
        # Such trips have an estimated GPS distance of 0 km.
        cursor.execute("""
            INSERT INTO TripDistance (
                trip_record_id,
                distance_km
            )
            SELECT
                t.trip_record_id,
                COALESCE(
                    SUM(
                        2 * 6371 * ASIN(
                            LEAST(
                                1,
                                SQRT(
                                    POW(
                                        SIN(RADIANS(
                                            p2.latitude - p1.latitude
                                        ) / 2),
                                        2
                                    )
                                    +
                                    COS(RADIANS(p1.latitude))
                                    * COS(RADIANS(p2.latitude))
                                    * POW(
                                        SIN(RADIANS(
                                            p2.longitude - p1.longitude
                                        ) / 2),
                                        2
                                    )
                                )
                            )
                        )
                    ),
                    0
                ) AS distance_km
            FROM Trip t
            LEFT JOIN GPSPoint p1
                ON t.trip_record_id = p1.trip_record_id
            LEFT JOIN GPSPoint p2
                ON p1.trip_record_id = p2.trip_record_id
                AND p2.point_index = p1.point_index + 1
            WHERE t.trip_record_id > %s
              AND t.trip_record_id <= %s
            GROUP BY t.trip_record_id
            ON DUPLICATE KEY UPDATE
                distance_km = VALUES(distance_km)
        """, (last_id, batch_end))

        connection.db_connection.commit()

        last_id = batch_end
        elapsed = (time.time() - start_time) / 60

        print(
            f"Processed through trip {last_id:,} "
            f"of {max_id:,} | "
            f"Elapsed: {elapsed:.1f} min",
            flush=True
        )

    cursor.execute("""
        SELECT COUNT(*)
        FROM TripDistance
    """)

    print(
        "\nTrips with calculated distance:",
        cursor.fetchone()[0]
    )

finally:
    connection.close_connection()