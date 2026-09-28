
from DbConnector import DbConnector
from tabulate import tabulate

connection = DbConnector()
cursor = connection.cursor

try:
    # --------------------------------------------------
    # QUESTION 1
    # How many taxis, trips, and total GPS points?
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            COUNT(DISTINCT taxi_id) AS total_taxis,
            COUNT(*) AS total_trips,
            SUM(num_points) AS total_gps_points
        FROM Trip
    """)

    print("\nQUESTION 1")
    print(tabulate(
        cursor.fetchall(),
        headers=cursor.column_names,
        tablefmt="grid"
    ))

    # --------------------------------------------------
    # QUESTION 2
    # Average number of trips per taxi
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            ROUND(AVG(trip_count), 2) AS avg_trips_per_taxi
        FROM (
            SELECT taxi_id, COUNT(*) AS trip_count
            FROM Trip
            GROUP BY taxi_id
        ) AS taxi_trips
    """)

    print("\nQUESTION 2")
    print(tabulate(
        cursor.fetchall(),
        headers=cursor.column_names,
        tablefmt="grid"
    ))

    # --------------------------------------------------
    # QUESTION 3
    # Top 20 taxis with the most trips
    # --------------------------------------------------

    cursor.execute("""
        SELECT
            taxi_id,
            COUNT(*) AS number_of_trips
        FROM Trip
        GROUP BY taxi_id
        ORDER BY number_of_trips DESC
        LIMIT 20
    """)

    print("\nQUESTION 3")
    print(tabulate(
        cursor.fetchall(),
        headers=cursor.column_names,
        tablefmt="grid"
    ))

    # --------------------------------------------------
    # QUESTION 4a
    # Most used call type per taxi
    # --------------------------------------------------

    cursor.execute("""
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

    print("\nQUESTION 4a")
    print(tabulate(
        cursor.fetchall(),
        headers=cursor.column_names,
        tablefmt="grid"
    ))

finally:
    connection.close_connection()
    