import time
from DbConnector import DbConnector


BATCH_SIZE = 5000


def main():
    connection = DbConnector()
    cursor = connection.cursor
    db = connection.db_connection

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS TripDistance (
                trip_record_id BIGINT PRIMARY KEY,
                distance_km DOUBLE NOT NULL,
                FOREIGN KEY (trip_record_id)
                    REFERENCES Trip(trip_record_id)
            ) ENGINE = InnoDB
        """)

        # Resume after the last completed batch.
        # Assumes previous results are complete and GPS data is unchanged.
        cursor.execute("""
            SELECT COALESCE(MAX(trip_record_id), 0)
            FROM TripDistance
        """)
        last_id = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COALESCE(MAX(trip_record_id), 0)
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

            rows = cursor.fetchall()
            if not rows:
                break

            batch_end = rows[-1][0]

            # Sum Haversine distances between consecutive GPS points.
            # Trips with 0 or 1 point receive an estimated distance of 0.
            cursor.execute("""
                INSERT INTO TripDistance (trip_record_id, distance_km)
                SELECT
                    t.trip_record_id,
                    COALESCE(
                        SUM(
                            2 * 6371 * ASIN(
                                LEAST(1, SQRT(
                                    POW(SIN(RADIANS(
                                        p2.latitude - p1.latitude
                                    ) / 2), 2)
                                    + COS(RADIANS(p1.latitude))
                                    * COS(RADIANS(p2.latitude))
                                    * POW(SIN(RADIANS(
                                        p2.longitude - p1.longitude
                                    ) / 2), 2)
                                ))
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

            db.commit()
            last_id = batch_end
            elapsed = (time.time() - start_time) / 60

            print(
                f"Processed through trip {last_id:,} of {max_id:,} | "
                f"Elapsed: {elapsed:.1f} min",
                flush=True
            )

        cursor.execute("SELECT COUNT(*) FROM TripDistance")
        print("\nTrips with calculated distance:", cursor.fetchone()[0])

    finally:
        connection.close_connection()


if __name__ == "__main__":
    main()