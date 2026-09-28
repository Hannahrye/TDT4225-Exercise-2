
from DbConnector import DbConnector
from tabulate import tabulate

connection = DbConnector()
cursor = connection.cursor

try:
    # Unix timestamps are stored in UTC.
    cursor.execute("SET time_zone = '+00:00'")

    # Check that the Porto timezone is available.
    cursor.execute("""
        SELECT CONVERT_TZ(
            '2026-07-01 12:00:00',
            '+00:00',
            'Europe/Lisbon'
        )
    """)

    if cursor.fetchone()[0] is None:
        raise RuntimeError("MySQL timezone data is missing.")

    # QUESTION 4b
    cursor.execute("""
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
            ROUND(AVG(duration_minutes), 2)
                AS avg_duration_minutes,
            ROUND(AVG(distance_km), 2)
                AS avg_distance_km,

            ROUND(
                100 * AVG(start_hour >= 0
                          AND start_hour < 6), 2
            ) AS pct_00_06,

            ROUND(
                100 * AVG(start_hour >= 6
                          AND start_hour < 12), 2
            ) AS pct_06_12,

            ROUND(
                100 * AVG(start_hour >= 12
                          AND start_hour < 18), 2
            ) AS pct_12_18,

            ROUND(
                100 * AVG(start_hour >= 18
                          AND start_hour < 24), 2
            ) AS pct_18_24

        FROM trip_metrics
        GROUP BY call_type
        ORDER BY call_type
    """)

    print("\nQUESTION 4b: COMPLETE RESULTS")
    print(tabulate(
        cursor.fetchall(),
        headers=cursor.column_names,
        tablefmt="grid"
    ))

finally:
    connection.close_connection()