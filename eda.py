
"""
TDT4225 - Assignment 2
Exploratory Data Analysis: Porto Taxi Trajectory Dataset

Outputs are saved in the eda_results directory.

"""

from pathlib import Path
import json
import math
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

FILE_PATH = Path("porto/porto/porto.csv")
OUTPUT_DIR = Path("eda_results")
OUTPUT_DIR.mkdir(exist_ok=True)

# Porto City Hall, used as an approximate geographic centre.
# Coordinates are always stored as (latitude, longitude) here.
PORTO = (41.15794, -8.62911)

# Exploratory thresholds, NOT automatic deletion rules.
DISTANCE_THRESHOLD_KM = 50
LONG_TRIP_THRESHOLD_MIN = 180
HIGH_SPEED_THRESHOLD_KMH = 150

# GPS points are sampled every 15 seconds.
SAMPLING_INTERVAL = 15

# Batch size for processing trajectories.
CHUNK_SIZE = 10000


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def heading(title):
    print("\n" + "=" * 65)
    print(title)
    print("=" * 65)


def save_table(data, filename):
    """Save a DataFrame as CSV."""
    data.to_csv(OUTPUT_DIR / filename, index=False)


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Vectorized Haversine distance in kilometres.
    Accepts scalars or NumPy arrays.
    """
    r = 6371.0088

    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return 2 * r * np.arcsin(
        np.sqrt(np.clip(a, 0, 1))
    )


def parse_polyline(value):
    """
    Return a validated NumPy array of shape (N, 2),
    containing longitude and latitude.

    Returns None for malformed trajectories.
    Empty trajectories are valid JSON and return (0, 2).
    """
    if pd.isna(value):
        return None

    try:
        points = json.loads(value)

        if not isinstance(points, list):
            return None

        if len(points) == 0:
            return np.empty((0, 2), dtype=float)

        arr = np.asarray(points, dtype=float)

        if arr.ndim != 2 or arr.shape[1] != 2:
            return None

        if not np.isfinite(arr).all():
            return None

        return arr

    except (ValueError, TypeError, OverflowError):
        return None


# ============================================================
# 1. LOAD DATA
# ============================================================

start = time.time()

heading("1. LOAD DATA")

df = pd.read_csv(
    FILE_PATH,
    dtype={
        "TRIP_ID": "string",
        "TAXI_ID": "string",
        "CALL_TYPE": "string",
        "DAY_TYPE": "string"
    }
)

print("Number of trips:", len(df))
print("\nColumns:")
print(df.columns.tolist())

print("\nData types:")
print(df.dtypes)

print("\nFirst five rows:")
print(df.drop(columns=["POLYLINE"]).head().to_string())

print("\nMemory usage (MB):")
print(round(
    df.memory_usage(deep=True).sum() / 1024**2,
    2
))


# ============================================================
# 2. BASIC DATA QUALITY
# ============================================================

heading("2. BASIC DATA QUALITY")

print("\nMissing values:")
print(df.isna().sum().to_string())

print("\nDuplicate TRIP_ID:")
print(df["TRIP_ID"].duplicated().sum())

print("\nCompletely duplicated rows:")
print(df.duplicated().sum())

print("\nUnique taxis:")
print(df["TAXI_ID"].nunique())

print("\nMissing TAXI_ID:")
print(df["TAXI_ID"].isna().sum())

print("\nCALL_TYPE distribution:")
print(df["CALL_TYPE"].value_counts(dropna=False))

print("\nDAY_TYPE distribution:")
print(df["DAY_TYPE"].value_counts(dropna=False))

print("\nMISSING_DATA distribution:")
print(df["MISSING_DATA"].value_counts(dropna=False))

print("\nMissing ORIGIN_CALL by CALL_TYPE:")
print(
    df.groupby("CALL_TYPE")["ORIGIN_CALL"]
    .apply(lambda x: x.isna().sum())
)

print("\nMissing ORIGIN_STAND by CALL_TYPE:")
print(
    df.groupby("CALL_TYPE")["ORIGIN_STAND"]
    .apply(lambda x: x.isna().sum())
)

print("\nTrips per taxi:")
trips_per_taxi = (
    df.groupby("TAXI_ID")
    .size()
    .sort_values(ascending=False)
)

print(trips_per_taxi.describe())

print("\nTop 20 taxis by number of trips:")
print(trips_per_taxi.head(20))

save_table(
    trips_per_taxi.rename("NUM_TRIPS").reset_index(),
    "trips_per_taxi.csv"
)


# ============================================================
# 3. TIMESTAMPS
# ============================================================

heading("3. TIMESTAMPS")

# Unix timestamps are interpreted as UTC.
df["START_TIME_UTC"] = pd.to_datetime(
    df["TIMESTAMP"],
    unit="s",
    utc=True,
    errors="coerce"
)

# Convert to Porto local time, including daylight saving.
df["START_TIME_LOCAL"] = (
    df["START_TIME_UTC"]
    .dt.tz_convert("Europe/Lisbon")
)

print("\nMissing timestamps:")
print(df["TIMESTAMP"].isna().sum())

print("\nInvalid timestamps:")
print(df["START_TIME_UTC"].isna().sum())

print("\nFirst recorded trip:")
print(df["START_TIME_LOCAL"].min())

print("\nLast recorded trip:")
print(df["START_TIME_LOCAL"].max())

monthly_trips = (
    df.groupby(
        df["START_TIME_LOCAL"]
        .dt.tz_localize(None)
        .dt.to_period("M")
    )
    .size()
)

print("\nTrips per month:")
print(monthly_trips)

save_table(
    monthly_trips.rename("NUM_TRIPS").reset_index(),
    "monthly_trips.csv"
)

hourly_trips = (
    df.groupby(df["START_TIME_LOCAL"].dt.hour)
    .size()
    .reindex(range(24), fill_value=0)
)

print("\nTrips by starting hour:")
print(hourly_trips)

save_table(
    hourly_trips.rename("NUM_TRIPS").reset_index(),
    "hourly_trips.csv"
)


# ============================================================
# 4. ANALYSE POLYLINE
# ============================================================

heading("4. POLYLINE ANALYSIS")

# Arrays are preallocated to avoid repeatedly expanding
# the main DataFrame during the trajectory analysis.

n = len(df)

num_points = np.zeros(n, dtype=np.int32)
invalid_coords = np.zeros(n, dtype=np.int32)
malformed = np.zeros(n, dtype=bool)

total_distance = np.full(n, np.nan)
max_speed = np.full(n, np.nan)

far_points = np.zeros(n, dtype=np.int32)
max_distance_porto = np.full(n, np.nan)

start_lon = np.full(n, np.nan)
start_lat = np.full(n, np.nan)
end_lon = np.full(n, np.nan)
end_lat = np.full(n, np.nan)

total_gps_points = 0
total_invalid_points = 0
total_far_points = 0

porto_lat, porto_lon = PORTO

for chunk_start in range(0, n, CHUNK_SIZE):

    chunk_end = min(chunk_start + CHUNK_SIZE, n)

    for i in range(chunk_start, chunk_end):

        points = parse_polyline(
            df["POLYLINE"].iat[i]
        )

        if points is None:
            malformed[i] = True
            continue

        count = len(points)
        num_points[i] = count
        total_gps_points += count

        if count == 0:
            continue

        lon = points[:, 0]
        lat = points[:, 1]

        # Check legal coordinate ranges.
        valid = (
            (lon >= -180) & (lon <= 180)
            & (lat >= -90) & (lat <= 90)
        )

        invalid_count = int((~valid).sum())

        invalid_coords[i] = invalid_count
        total_invalid_points += invalid_count

        # Keep original point count, but do not compute
        # geographical metrics using invalid coordinates.
        if invalid_count > 0:
            continue

        start_lon[i] = lon[0]
        start_lat[i] = lat[0]
        end_lon[i] = lon[-1]
        end_lat[i] = lat[-1]

        # Distance from each point to Porto.
        distances_porto = haversine_km(
            porto_lat,
            porto_lon,
            lat,
            lon
        )

        far = distances_porto > DISTANCE_THRESHOLD_KM

        far_points[i] = int(far.sum())
        total_far_points += far_points[i]

        max_distance_porto[i] = float(
            distances_porto.max()
        )

        # Calculate distance between consecutive points.
        if count >= 2:

            segment_distances = haversine_km(
                lat[:-1],
                lon[:-1],
                lat[1:],
                lon[1:]
            )

            total_distance[i] = float(
                segment_distances.sum()
            )

            # km/h = km / (15 / 3600 hours)
            speeds = (
                segment_distances
                * 3600 / SAMPLING_INTERVAL
            )

            max_speed[i] = float(speeds.max())

    print(
        f"Processed {chunk_end:,} / {n:,} trips",
        end="\r"
    )

print("\nTrajectory processing completed.")


# ============================================================
# 5. ADD TRAJECTORY METRICS
# ============================================================

heading("5. TRAJECTORY METRICS")

df["NUM_POINTS"] = num_points
df["MALFORMED_POLYLINE"] = malformed
df["INVALID_COORDS"] = invalid_coords

df["DURATION_MIN"] = (
    np.maximum(num_points - 1, 0)
    * SAMPLING_INTERVAL / 60
)

df["TOTAL_DISTANCE_KM"] = total_distance
df["MAX_SPEED_KMH"] = max_speed

df["FAR_POINTS"] = far_points
df["MAX_DISTANCE_PORTO_KM"] = max_distance_porto

df["START_LON"] = start_lon
df["START_LAT"] = start_lat
df["END_LON"] = end_lon
df["END_LAT"] = end_lat

df["FAR_SHARE"] = np.divide(
    far_points,
    num_points,
    out=np.zeros(n, dtype=float),
    where=num_points > 0
)

df["IS_VALID_BY_POINT_COUNT"] = (
    df["NUM_POINTS"] >= 3
)

print("\nTotal GPS points:")
print(f"{total_gps_points:,}")

print("\nMalformed trajectories:")
print(int(malformed.sum()))

print("\nInvalid GPS points:")
print(total_invalid_points)

print("\nTrips containing invalid coordinates:")
print(int((invalid_coords > 0).sum()))

print("\nGPS points per trip:")
print(df["NUM_POINTS"].describe())

print("\nTrips with 0, 1 or 2 points:")
print(
    df["NUM_POINTS"]
    .value_counts()
    .reindex([0, 1, 2], fill_value=0)
)

print("\nInvalid trips (< 3 points):")
print(int((df["NUM_POINTS"] < 3).sum()))


# ============================================================
# 6. TRIP DURATION
# ============================================================

heading("6. TRIP DURATION")

# This mask is for exploratory analysis, not a
# permanent rule for deleting observations.
usable = (
    (df["NUM_POINTS"] >= 3)
    & (~df["MALFORMED_POLYLINE"])
    & (df["INVALID_COORDS"] == 0)
)

print("\nDuration statistics (minutes):")
print(
    df.loc[usable, "DURATION_MIN"].describe(
        percentiles=[0.5, 0.9, 0.95, 0.99]
    )
)

long_trips = df.loc[
    usable
    & (
        df["DURATION_MIN"]
        > LONG_TRIP_THRESHOLD_MIN
    )
]

print("\nTrips longer than 3 hours:")
print(len(long_trips))

print("\n10 longest trips:")
print(
    df.loc[usable]
    .nlargest(10, "DURATION_MIN")[
        [
            "TRIP_ID",
            "TAXI_ID",
            "NUM_POINTS",
            "DURATION_MIN",
            "TOTAL_DISTANCE_KM",
            "MISSING_DATA"
        ]
    ].to_string(index=False)
)


# ============================================================
# 7. GEOGRAPHIC OUTLIERS
# ============================================================

heading("7. GEOGRAPHIC OUTLIERS")

geo_outliers = df.loc[
    df["FAR_POINTS"] > 0
].copy()

print("\nTrips with points > 50 km from Porto:")
print(len(geo_outliers))

print("\nTotal points > 50 km from Porto:")
print(total_far_points)

print("\nMaximum distance from Porto (km):")
print(df["MAX_DISTANCE_PORTO_KM"].max())

print("\nOutlier statistics:")
print(
    geo_outliers[
        ["FAR_SHARE", "MAX_DISTANCE_PORTO_KM"]
    ].describe()
)

print("\nTrips with more than 50% far-away points:")
print(
    int((geo_outliers["FAR_SHARE"] > 0.5).sum())
)

print("\nTrips with exactly one far-away point:")
print(
    int((geo_outliers["FAR_POINTS"] == 1).sum())
)

print("\nGeographic outliers with MISSING_DATA=True:")
print(
    int(
        geo_outliers["MISSING_DATA"]
        .fillna(False)
        .astype(bool)
        .sum()
    )
)

print("\n10 largest geographic deviations:")
print(
    geo_outliers.nlargest(
        10, "MAX_DISTANCE_PORTO_KM"
    )[
        [
            "TRIP_ID",
            "NUM_POINTS",
            "FAR_POINTS",
            "FAR_SHARE",
            "MAX_DISTANCE_PORTO_KM",
            "MISSING_DATA"
        ]
    ].to_string(index=False)
)

save_table(
    geo_outliers.drop(columns=["POLYLINE"]),
    "geographic_outliers.csv"
)


# ============================================================
# 8. DISTANCE AND UNREALISTIC GPS JUMPS
# ============================================================

heading("8. DISTANCE AND GPS JUMPS")

print("\nDistance statistics (km):")
print(
    df.loc[usable, "TOTAL_DISTANCE_KM"]
    .describe(
        percentiles=[0.5, 0.9, 0.95, 0.99]
    )
)

high_speed = df.loc[
    usable
    & (
        df["MAX_SPEED_KMH"]
        > HIGH_SPEED_THRESHOLD_KMH
    )
]

print("\nTrips containing segments above 150 km/h:")
print(len(high_speed))

print("\n10 trips with highest calculated speed:")
print(
    df.loc[usable]
    .nlargest(10, "MAX_SPEED_KMH")[
        [
            "TRIP_ID",
            "NUM_POINTS",
            "TOTAL_DISTANCE_KM",
            "MAX_SPEED_KMH",
            "FAR_POINTS",
            "MISSING_DATA"
        ]
    ].to_string(index=False)
)

print(
    "\nNote: High speed indicates a possible GPS error, "
    "not necessarily an invalid trip."
)


# ============================================================
# 9. MISSING DATA AND QUALITY FLAGS
# ============================================================

heading("9. DATA QUALITY OVERLAP")

# Keep separate flags so the same trip can belong
# to several categories.

quality_flags = pd.DataFrame({
    "TRIP_ID": df["TRIP_ID"],
    "MISSING_DATA": df["MISSING_DATA"],
    "FEWER_THAN_3_POINTS": df["NUM_POINTS"] < 3,
    "MALFORMED_POLYLINE": df["MALFORMED_POLYLINE"],
    "INVALID_COORDS": df["INVALID_COORDS"] > 0,
    "GEOGRAPHIC_OUTLIER": df["FAR_POINTS"] > 0,
    "LONG_TRIP": (
        df["DURATION_MIN"]
        > LONG_TRIP_THRESHOLD_MIN
    ),
    "HIGH_SPEED": (
        df["MAX_SPEED_KMH"]
        > HIGH_SPEED_THRESHOLD_KMH
    )
})

print("\nNumber of trips by quality flag:")
print(
    quality_flags.drop(columns=["TRIP_ID"])
    .sum(numeric_only=True)
)

print("\nMISSING_DATA vs fewer than 3 points:")
print(
    pd.crosstab(
        quality_flags["MISSING_DATA"],
        quality_flags["FEWER_THAN_3_POINTS"]
    )
)

print("\nMISSING_DATA vs geographic outliers:")
print(
    pd.crosstab(
        quality_flags["MISSING_DATA"],
        quality_flags["GEOGRAPHIC_OUTLIER"]
    )
)

save_table(
    quality_flags,
    "quality_flags.csv"
)


# ============================================================
# 10. SAVE METRICS FOR DATABASE DESIGN
# ============================================================

heading("10. SAVE RESULTS")

# Save derived metrics without duplicating the very large
# POLYLINE strings in the output.

metrics_columns = [
    "TRIP_ID",
    "TAXI_ID",
    "CALL_TYPE",
    "ORIGIN_CALL",
    "ORIGIN_STAND",
    "TIMESTAMP",
    "DAY_TYPE",
    "MISSING_DATA",
    "NUM_POINTS",
    "MALFORMED_POLYLINE",
    "INVALID_COORDS",
    "DURATION_MIN",
    "TOTAL_DISTANCE_KM",
    "MAX_SPEED_KMH",
    "FAR_POINTS",
    "FAR_SHARE",
    "MAX_DISTANCE_PORTO_KM",
    "START_LON",
    "START_LAT",
    "END_LON",
    "END_LAT",
    "IS_VALID_BY_POINT_COUNT"
]

save_table(
    df[metrics_columns],
    "trip_metrics.csv"
)

print("\nSaved trip_metrics.csv")
print("Saved quality_flags.csv")
print("Saved geographic_outliers.csv")


# ============================================================
# 11. CREATE FIGURES
# ============================================================

heading("11. CREATE FIGURES")

# CALL_TYPE distribution
plt.figure(figsize=(7, 4))

df["CALL_TYPE"].value_counts().sort_index().plot(
    kind="bar"
)

plt.title("Distribution of call types")
plt.xlabel("Call type")
plt.ylabel("Number of trips")
plt.xticks(rotation=0)
plt.tight_layout()

plt.savefig(
    OUTPUT_DIR / "call_type_distribution.png",
    dpi=200
)
plt.close()


# GPS point distribution
plt.figure(figsize=(8, 4))

df.loc[
    df["NUM_POINTS"] <= 200,
    "NUM_POINTS"
].hist(bins=50)

plt.title("GPS points per trip")
plt.xlabel("Number of GPS points")
plt.ylabel("Number of trips")
plt.tight_layout()

plt.savefig(
    OUTPUT_DIR / "gps_points_distribution.png",
    dpi=200
)
plt.close()

# ---------------------------------------------------------
# MISSING_DATA vs number of GPS points
# ---------------------------------------------------------

# Group trips by number of GPS points
df["GPS_POINT_GROUP"] = pd.cut(
    df["NUM_POINTS"],
    bins=[-1, 0, 1, 2, float("inf")],
    labels=["0", "1", "2", "3 or more"]
)

# Compare GPS point groups with MISSING_DATA
missing_vs_gps = pd.crosstab(
    df["GPS_POINT_GROUP"],
    df["MISSING_DATA"]
)

print("\nMISSING_DATA vs number of GPS points:")
print(missing_vs_gps)

# Specifically check trips with fewer than 3 GPS points
few_points = df[df["NUM_POINTS"] < 3]

print("\nTrips with fewer than 3 GPS points:")
print(f"Total: {len(few_points)}")
print(few_points["MISSING_DATA"].value_counts())

# Trip duration distribution
plt.figure(figsize=(8, 4))

df.loc[
    usable & (df["DURATION_MIN"] <= 120),
    "DURATION_MIN"
].hist(bins=60)

plt.title("Trip duration distribution")
plt.xlabel("Duration (minutes)")
plt.ylabel("Number of trips")
plt.tight_layout()

plt.savefig(
    OUTPUT_DIR / "trip_duration_distribution.png",
    dpi=200
)
plt.close()



# Monthly trips
plt.figure(figsize=(10, 4))

monthly_trips.plot(kind="bar")

plt.title("Number of trips per month")
plt.xlabel("Month")
plt.ylabel("Number of trips")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()

plt.savefig(
    OUTPUT_DIR / "monthly_trips.png",
    dpi=200
)
plt.close()


# Hourly trips
plt.figure(figsize=(8, 4))

hourly_trips.plot(kind="bar")

plt.title("Trip starts by hour of day")
plt.xlabel("Hour (Porto local time)")
plt.ylabel("Number of trips")
plt.xticks(rotation=0)
plt.tight_layout()

plt.savefig(
    OUTPUT_DIR / "hourly_trips.png",
    dpi=200
)
plt.close()


# Distance distribution, capped for readability
plt.figure(figsize=(8, 4))

df.loc[
    usable
    & (df["TOTAL_DISTANCE_KM"] <= 50),
    "TOTAL_DISTANCE_KM"
].hist(bins=50)

plt.title("Trip distance distribution")
plt.xlabel("Calculated distance (km)")
plt.ylabel("Number of trips")
plt.tight_layout()

plt.savefig(
    OUTPUT_DIR / "trip_distance_distribution.png",
    dpi=200
)
plt.close()

print("\nFigures saved.")


# ============================================================
# 12. FINAL SUMMARY
# ============================================================

heading("12. FINAL EDA SUMMARY")

summary = {
    "total_trips": len(df),
    "unique_taxis": df["TAXI_ID"].nunique(),
    "duplicate_trip_ids": int(
        df["TRIP_ID"].duplicated().sum()
    ),
    "total_gps_points": total_gps_points,
    "trips_fewer_than_3_points": int(
        (df["NUM_POINTS"] < 3).sum()
    ),
    "malformed_trajectories": int(
        df["MALFORMED_POLYLINE"].sum()
    ),
    "invalid_gps_points": total_invalid_points,
    "geographic_outlier_trips": len(geo_outliers),
    "geographic_outlier_points": total_far_points,
    "trips_longer_than_3_hours": len(long_trips),
    "trips_with_high_speed_segments": len(high_speed),
    "average_duration_min": float(
        df.loc[usable, "DURATION_MIN"].mean()
    ),
    "median_duration_min": float(
        df.loc[usable, "DURATION_MIN"].median()
    )
}

with open(
    OUTPUT_DIR / "eda_summary.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
    summary,
    f,
    indent=4,
    default=lambda x: x.item() if isinstance(x, np.generic) else str(x)
)

for key, value in summary.items():
    print(f"{key}: {value}")

elapsed = time.time() - start

print(f"\nTotal execution time: {elapsed:.1f} seconds")
print(f"\nAll results saved in: {OUTPUT_DIR.resolve()}")
print("\nEDA completed.")