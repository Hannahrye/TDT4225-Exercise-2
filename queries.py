from DbConnector import DbConnector
from tabulate import tabulate


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
                SUM(num_points) AS total_gps_points
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

    finally:
        connection.close_connection()


if __name__ == "__main__":
    main()