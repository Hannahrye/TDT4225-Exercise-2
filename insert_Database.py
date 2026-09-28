
import csv
import json
import time
from collections import Counter

from DbConnector import DbConnector


CSV_FILE = "porto/porto/porto.csv"

# Use 1000 for another test, or None for the entire dataset.
MAX_TRIPS = None

TRIP_BATCH_SIZE = 1000
GPS_BATCH_SIZE = 10000


def get_duplicate_ids():
    """Find original TRIP_IDs that occur more than once."""
    counts = Counter()

    with open(CSV_FILE, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            counts[row["TRIP_ID"]] += 1

    return {
        trip_id
        for trip_id, count in counts.items()
        if count > 1
    }


def optional_int(value):
    return int(value) if value else None


def main():
    start_time = time.time()

    print("Checking duplicate IDs...")
    duplicate_ids = get_duplicate_ids()
    print(f"Duplicated TRIP_IDs: {len(duplicate_ids)}")

    connection = DbConnector()
    db = connection.db_connection
    cursor = connection.cursor

    trip_query = """
        INSERT INTO Trip (
            trip_record_id,
            trip_id,
            taxi_id,
            call_type,
            origin_call,
            origin_stand,
            start_timestamp,
            day_type,
            missing_data,
            num_points,
            duplicate_id
        )
        VALUES (%s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s)
    """

    gps_query = """
        INSERT INTO GPSPoint (
            trip_record_id,
            point_index,
            longitude,
            latitude
        )
        VALUES (%s, %s, %s, %s)
    """

    trip_batch = []
    gps_batch = []

    seen_duplicate_rows = set()

    trip_record_id = 0
    inserted_trips = 0
    inserted_points = 0
    removed_identical_rows = 0

    try:
        # Prevent accidentally loading data into nonempty tables.
        cursor.execute("SELECT COUNT(*) FROM Trip")
        existing_trips = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM GPSPoint")
        existing_points = cursor.fetchone()[0]

        if existing_trips or existing_points:
            raise RuntimeError(
                "Tables are not empty. Run reset_tables.py first."
            )

        with open(
            CSV_FILE,
            newline="",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:
                original_id = row["TRIP_ID"]

                # Only check complete-row duplicates for IDs
                # that occur more than once.
                if original_id in duplicate_ids:
                    signature = tuple(
                        row[column]
                        for column in reader.fieldnames
                    )

                    if signature in seen_duplicate_rows:
                        removed_identical_rows += 1
                        continue

                    seen_duplicate_rows.add(signature)

                polyline = json.loads(row["POLYLINE"])

                trip_record_id += 1

                trip_batch.append((
                    trip_record_id,
                    original_id,
                    row["TAXI_ID"],
                    row["CALL_TYPE"],
                    optional_int(row["ORIGIN_CALL"]),
                    optional_int(row["ORIGIN_STAND"]),
                    int(row["TIMESTAMP"]),
                    row["DAY_TYPE"],
                    row["MISSING_DATA"].lower() == "true",
                    len(polyline),
                    original_id in duplicate_ids
                ))

                for index, point in enumerate(polyline):
                    longitude, latitude = point

                    gps_batch.append((
                        trip_record_id,
                        index,
                        longitude,
                        latitude
                    ))

                # Insert complete batches in the correct order:
                # first trips, then their GPS points.
                if (
                    len(trip_batch) >= TRIP_BATCH_SIZE
                    or len(gps_batch) >= GPS_BATCH_SIZE
                ):
                    cursor.executemany(trip_query, trip_batch)
                    cursor.executemany(gps_query, gps_batch)

                    db.commit()

                    inserted_trips += len(trip_batch)
                    inserted_points += len(gps_batch)

                    trip_batch.clear()
                    gps_batch.clear()

                    if inserted_trips % 10000 < TRIP_BATCH_SIZE:
                        elapsed = (time.time() - start_time) / 60

                        print(
                            f"{inserted_trips:,} trips | "
                            f"{inserted_points:,} GPS points | "
                            f"{elapsed:.1f} min"
                        )

                if (
                    MAX_TRIPS is not None
                    and trip_record_id >= MAX_TRIPS
                ):
                    break

        # Insert the final, incomplete batch.
        if trip_batch:
            cursor.executemany(trip_query, trip_batch)
            cursor.executemany(gps_query, gps_batch)

            db.commit()

            inserted_trips += len(trip_batch)
            inserted_points += len(gps_batch)

        elapsed = (time.time() - start_time) / 60

        print("\nIMPORT COMPLETE")
        print(f"Trips: {inserted_trips:,}")
        print(f"GPS points: {inserted_points:,}")
        print(
            f"Identical duplicate rows removed: "
            f"{removed_identical_rows}"
        )
        print(f"Elapsed time: {elapsed:.1f} minutes")

    except Exception:
        db.rollback()
        raise

    finally:
        connection.close_connection()


if __name__ == "__main__":
    main()