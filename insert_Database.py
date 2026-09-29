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


TRIP_QUERY = """
    INSERT INTO Trip (
        trip_record_id, trip_id, taxi_id, call_type, origin_call,
        origin_stand, start_timestamp, day_type, missing_data,
        num_points, duplicate_id
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

GPS_QUERY = """
    INSERT INTO GPSPoint (trip_record_id, point_index, longitude, latitude)
    VALUES (%s, %s, %s, %s)
"""


def get_duplicate_ids():
    """Find original TRIP_IDs that occur more than once."""
    counts = Counter()

    with open(CSV_FILE, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            counts[row["TRIP_ID"]] += 1

    return {trip_id for trip_id, count in counts.items() if count > 1}


def optional_int(value):
    return int(value) if value else None


def insert_batch(cursor, db, trip_batch, gps_batch):
    """Insert trips before GPS points, then commit the batch together."""
    if not trip_batch:
        return 0, 0

    cursor.executemany(TRIP_QUERY, trip_batch)
    if gps_batch:
        cursor.executemany(GPS_QUERY, gps_batch)
    db.commit()

    trips, points = len(trip_batch), len(gps_batch)
    trip_batch.clear()
    gps_batch.clear()
    return trips, points


def main():
    start_time = time.time()

    print("Checking duplicate IDs...")
    duplicate_ids = get_duplicate_ids()
    print(f"Duplicated TRIP_IDs: {len(duplicate_ids)}")

    connection = DbConnector()
    db = connection.db_connection
    cursor = connection.cursor

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
                "Import stopped: Trip and GPSPoint must be empty before import."
            )

        with open(CSV_FILE, newline="", encoding="utf-8") as file:

            reader = csv.DictReader(file)

            for row in reader:
                original_id = row["TRIP_ID"]

                # Only check complete-row duplicates for IDs
                # that occur more than once.
                if original_id in duplicate_ids:
                    signature = tuple(row[column] for column in reader.fieldnames)

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

                for index, (longitude, latitude) in enumerate(polyline):
                    gps_batch.append((trip_record_id, index, longitude, latitude))

                # Insert complete batches in the correct order:
                # first trips, then their GPS points.
                if (
                    len(trip_batch) >= TRIP_BATCH_SIZE
                    or len(gps_batch) >= GPS_BATCH_SIZE
                ):
                    trips, points = insert_batch(cursor, db, trip_batch, gps_batch)
                    inserted_trips += trips
                    inserted_points += points

                    if inserted_trips % 10000 < TRIP_BATCH_SIZE:
                        elapsed = (time.time() - start_time) / 60

                        print(
                            f"{inserted_trips:,} trips | "
                            f"{inserted_points:,} GPS points | "
                            f"{elapsed:.1f} min"
                        )

                if MAX_TRIPS is not None and trip_record_id >= MAX_TRIPS:
                    break

        # Insert any remaining rows after the loop.
        trips, points = insert_batch(cursor, db, trip_batch, gps_batch)
        inserted_trips += trips
        inserted_points += points

        elapsed = (time.time() - start_time) / 60

        print("\nIMPORT COMPLETE")
        print(f"Trips: {inserted_trips:,}")
        print(f"GPS points: {inserted_points:,}")
        print(f"Identical duplicate rows removed: {removed_identical_rows}")
        print(f"Elapsed time: {elapsed:.1f} minutes")

    # Rollback affects only the current batch; earlier commits remain stored.
    except Exception:
        db.rollback()
        raise

    finally:
        connection.close_connection()


if __name__ == "__main__":
    main()