import time
from haversine import haversine
from DbConnector import DbConnector


BATCH_SIZE = 5000


def trip_distance_km(points):
    """Sum of Haversine distances between consecutive (lat, lon) points.
    Trips with 0 or 1 point get distance 0."""
    return sum(
        haversine(points[i], points[i + 1])
        for i in range(len(points) - 1)
    )


def main():
    connection = DbConnector()
    cursor = connection.cursor
    db = connection.db_connection

    try:
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

            record_ids = [row[0] for row in cursor.fetchall()]
            if not record_ids:
                break

            batch_end = record_ids[-1]

            # Fetch all GPS points in the batch, in the original order.
            cursor.execute("""
                SELECT trip_record_id, latitude, longitude
                FROM GPSPoint
                WHERE trip_record_id > %s
                  AND trip_record_id <= %s
                ORDER BY trip_record_id, point_index
            """, (last_id, batch_end))

            # Group the points per trip. Trips without points keep
            # an empty list and get distance 0.
            points_per_trip = {record_id: [] for record_id in record_ids}
            for record_id, lat, lon in cursor.fetchall():
                points_per_trip[record_id].append((lat, lon))

            rows = [
                (record_id, trip_distance_km(points))
                for record_id, points in points_per_trip.items()
            ]

            cursor.executemany("""
                INSERT INTO TripDistance (trip_record_id, distance_km)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE
                    distance_km = VALUES(distance_km)
            """, rows)

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