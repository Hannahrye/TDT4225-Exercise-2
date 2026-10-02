from DbConnector import DbConnector
from tabulate import tabulate
from haversine import haversine, Unit


def run_query(cursor, title, query):
    cursor.execute(query)
    print(f"\n{title}")
    print(tabulate(
        cursor.fetchall(),
        headers=cursor.column_names,
        tablefmt="grid"
    ))


def main():
    connection = DbConnector()
    cursor = connection.cursor

    try:
        # 1. Number of taxis, trips and GPS points.
        run_query(cursor, "QUESTION 1", """
            SELECT
                COUNT(DISTINCT taxi_id) AS total_taxis,
                COUNT(*) AS total_trips,
                CAST(SUM(num_points) AS UNSIGNED) AS total_gps_points
            FROM Trip
        """)

        # 2. Average number of trips per taxi.
        run_query(cursor, "QUESTION 2", """
            SELECT
                ROUND(AVG(trip_count), 2) AS avg_trips_per_taxi
            FROM (
                SELECT taxi_id, COUNT(*) AS trip_count
                FROM Trip
                GROUP BY taxi_id
            ) AS taxi_trips
        """)

        # 3. Top 20 taxis by number of trips.
        run_query(cursor, "QUESTION 3", """
            SELECT
                taxi_id,
                COUNT(*) AS number_of_trips
            FROM Trip
            GROUP BY taxi_id
            ORDER BY number_of_trips DESC
            LIMIT 20
        """)

        # 4a. RANK preserves ties for the most used call type.
        run_query(cursor, "QUESTION 4a", """
            WITH call_counts AS (
                SELECT
                    taxi_id,
                    call_type,
                    COUNT(*) AS number_of_trips
                FROM Trip
                GROUP BY taxi_id, call_type
            ),
            ranked_calls AS (
                SELECT
                    taxi_id,
                    call_type,
                    number_of_trips,
                    RANK() OVER (
                        PARTITION BY taxi_id
                        ORDER BY number_of_trips DESC
                    ) AS call_rank
                FROM call_counts
            )
            SELECT
                taxi_id,
                call_type AS most_used_call_type,
                number_of_trips
            FROM ranked_calls
            WHERE call_rank = 1
            ORDER BY taxi_id
        """)

        # Interpret Unix timestamps in UTC before converting to local time.
        cursor.execute("SET time_zone = '+00:00'")
        cursor.execute("""
            SELECT CONVERT_TZ(
                '2026-07-01 12:00:00',
                '+00:00',
                'Europe/Lisbon'
            )
        """)

        if cursor.fetchone()[0] is None:
            raise RuntimeError("MySQL timezone data is missing.")

        # 4b. Duration, distance and local starting times by call type.
        run_query(cursor, "QUESTION 4b", """
            WITH trip_metrics AS (
                SELECT
                    t.call_type,
                    GREATEST(t.num_points - 1, 0) * 15 / 60.0
                        AS duration_minutes,
                    d.distance_km,
                    HOUR(
                        CONVERT_TZ(
                            FROM_UNIXTIME(t.start_timestamp),
                            '+00:00',
                            'Europe/Lisbon'
                        )
                    ) AS start_hour
                FROM Trip t
                JOIN TripDistance d
                    ON t.trip_record_id = d.trip_record_id
            )
            SELECT
                call_type,
                COUNT(*) AS number_of_trips,
                ROUND(AVG(duration_minutes), 2) AS avg_duration_minutes,
                ROUND(AVG(distance_km), 2) AS avg_distance_km,
                ROUND(
                    100 * AVG(start_hour >= 0 AND start_hour < 6), 2
                ) AS pct_00_06,
                ROUND(
                    100 * AVG(start_hour >= 6 AND start_hour < 12), 2
                ) AS pct_06_12,
                ROUND(
                    100 * AVG(start_hour >= 12 AND start_hour < 18), 2
                ) AS pct_12_18,
                ROUND(
                    100 * AVG(start_hour >= 18 AND start_hour < 24), 2
                ) AS pct_18_24
            FROM trip_metrics
            GROUP BY call_type
            ORDER BY call_type
        """)

        # 5. Taxies with most total hours and distance driven, sorted by hours
        run_query(cursor, "QUESTION 5", """
            SELECT
                t.taxi_id,
                COUNT(*) AS number_of_trips,
                ROUND(
                    SUM(GREATEST(t.num_points - 1, 0)) * 15 / 3600, 2
                ) AS total_hours,
                ROUND(SUM(d.distance_km), 2) AS total_distance_km
            FROM Trip t
            JOIN TripDistance d
                ON t.trip_record_id = d.trip_record_id
            GROUP BY t.taxi_id
            ORDER BY total_hours DESC
        """)

        # TODO må lese over denne!
        # 6. Trips that passed within 100 m of Porto City Hall.
        # The bounding box removes points that are clearly too far away
        # before the Haversine distance is calculated.
        run_query(cursor, "QUESTION 6", """
            SELECT
                t.trip_record_id,
                t.trip_id,
                t.taxi_id,
                ROUND(MIN(p.dist_m), 1) AS closest_distance_m,
                COUNT(*) OVER () AS total_trips_found
            FROM (
                SELECT
                    trip_record_id,
                    2 * 6371000 * ASIN(SQRT(
                        POW(SIN(RADIANS(latitude - 41.15794) / 2), 2)
                        + COS(RADIANS(41.15794)) * COS(RADIANS(latitude))
                        * POW(SIN(RADIANS(longitude + 8.62911) / 2), 2)
                    )) AS dist_m
                FROM GPSPoint
            ) AS p
            JOIN Trip t
                ON t.trip_record_id = p.trip_record_id
            WHERE p.dist_m <= 100
            GROUP BY t.trip_record_id, t.trip_id, t.taxi_id
            ORDER BY t.trip_record_id
            LIMIT 10
        """)

        # 7. Number of invalid trips
        run_query(cursor, "QUESTION 7", """
            SELECT 
                COUNT(*) AS invalid_trips
            FROM Trip 
            WHERE num_points < 3
        """)

        # 8. Trips that cross midnight
        run_query(cursor, "QUESTION 8", """
            WITH trip_times AS (
                SELECT
                    trip_record_id,
                    trip_id,
                    taxi_id,
                    CONVERT_TZ(
                        FROM_UNIXTIME(start_timestamp),
                        '+00:00', 'Europe/Lisbon'
                    ) AS start_local,
                    CONVERT_TZ(
                        FROM_UNIXTIME(
                            start_timestamp
                            + GREATEST(num_points - 1, 0) * 15
                        ),
                        '+00:00', 'Europe/Lisbon'
                    ) AS end_local
                FROM Trip
            )
            SELECT
                trip_record_id,
                trip_id,
                taxi_id,
                start_local,
                end_local,
                COUNT(*) OVER () AS total_midnight_crossers
            FROM trip_times
            WHERE DATE(end_local) > DATE(start_local)
            ORDER BY start_local
            LIMIT 20
        """)
        
        
        # 9. Circular trips: starts and ends within 50 m of each other.
        cursor.execute("""
            SELECT
                t.trip_record_id, t.trip_id, t.taxi_id, t.num_points,
                s.latitude, s.longitude, e.latitude, e.longitude
            FROM Trip t
            JOIN GPSPoint s
                ON s.trip_record_id = t.trip_record_id AND s.point_index = 0
            JOIN GPSPoint e
                ON e.trip_record_id = t.trip_record_id
                AND e.point_index = t.num_points - 1
            WHERE t.num_points >= 3
        """)
        circular = []
        for rid, tid, taxi, n, slat, slon, elat, elon in cursor.fetchall():
            dist = haversine((slat, slon), (elat, elon), unit=Unit.METERS)
            if dist <= 50:
                circular.append((rid, tid, taxi, n, round(dist, 1)))

        print("\nQUESTION 9")
        print(f"Circular trips: {len(circular):,}")
        print(tabulate(
            circular[:20],
            headers=["trip_record_id", "trip_id", "taxi_id",
                     "num_points", "start_end_distance_m"],
            tablefmt="grid"
        ))



    finally:
        connection.close_connection()


if __name__ == "__main__":
    main()