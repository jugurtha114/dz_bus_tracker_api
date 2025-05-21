"""
Periodic tasks for DZ Bus Tracker.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from tasks.base import RetryableTask

logger = logging.getLogger(__name__)


@shared_task(base=RetryableTask)
def cleanup_old_data():
    """
    Clean up old data across the application.
    """
    try:
        # Clean old location data
        from tasks.tracking import clean_old_location_data
        clean_old_location_data.delay()

        # Clean inactive buses
        from tasks.buses import clean_inactive_buses
        clean_inactive_buses.delay()

        # Clean old ratings
        from tasks.drivers import clean_old_ratings
        clean_old_ratings.delay()

        # Clean old notifications
        from tasks.notifications import clean_old_notifications
        clean_old_notifications.delay()

        # Clean inactive device tokens
        from tasks.notifications import clean_inactive_device_tokens
        clean_inactive_device_tokens.delay()

        logger.info("Scheduled cleanup of old data")
        return True

    except Exception as e:
        logger.error(f"Error scheduling cleanup: {e}")
        return False


@shared_task(base=RetryableTask)
def generate_daily_reports():
    """
    Generate daily reports for business analytics.
    """
    try:
        # Define report date (yesterday)
        report_date = timezone.now().date() - timedelta(days=1)

        # Generate passenger report
        passenger_report = generate_passenger_report(report_date)

        # Generate bus performance report
        bus_report = generate_bus_performance_report(report_date)

        # Generate driver performance report
        driver_report = generate_driver_performance_report(report_date)

        # Generate line performance report
        line_report = generate_line_performance_report(report_date)

        # Save reports
        save_reports(report_date, passenger_report, bus_report, driver_report, line_report)

        logger.info(f"Generated daily reports for {report_date}")
        return True

    except Exception as e:
        logger.error(f"Error generating daily reports: {e}")
        return False


def generate_passenger_report(report_date):
    """
    Generate passenger report for a specific date.
    """
    try:
        # Define date range
        start_date = timezone.datetime.combine(report_date, timezone.time.min)
        end_date = timezone.datetime.combine(report_date, timezone.time.max)

        # Get passenger counts
        from apps.tracking.models import PassengerCount
        passenger_counts = PassengerCount.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        )

        # Calculate statistics
        from django.db.models import Avg, Count, Max, Min, Sum

        total_counts = passenger_counts.count()

        if total_counts == 0:
            return {
                "date": report_date.isoformat(),
                "total_records": 0,
                "average_occupancy": 0,
                "max_occupancy": 0,
                "min_occupancy": 0,
                "total_passengers": 0,
                "peak_hour": None,
                "busiest_lines": [],
                "busiest_stops": [],
            }

        stats = passenger_counts.aggregate(
            avg_occupancy=Avg("occupancy_rate"),
            max_occupancy=Max("occupancy_rate"),
            min_occupancy=Min("occupancy_rate"),
            total_passengers=Sum("count"),
        )

        # Find peak hour
        from django.db.models.functions import TruncHour
        hourly_counts = passenger_counts.annotate(
            hour=TruncHour("created_at")
        ).values(
            "hour"
        ).annotate(
            total=Sum("count")
        ).order_by("-total")

        peak_hour = hourly_counts.first() if hourly_counts.exists() else None

        # Find busiest lines
        busiest_lines = passenger_counts.filter(
            line__isnull=False
        ).values(
            "line_id", "line__code", "line__name"
        ).annotate(
            total=Sum("count")
        ).order_by("-total")[:5]

        # Find busiest stops
        busiest_stops = passenger_counts.filter(
            stop__isnull=False
        ).values(
            "stop_id", "stop__name"
        ).annotate(
            total=Sum("count")
        ).order_by("-total")[:5]

        return {
            "date": report_date.isoformat(),
            "total_records": total_counts,
            "average_occupancy": stats["avg_occupancy"] or 0,
            "max_occupancy": stats["max_occupancy"] or 0,
            "min_occupancy": stats["min_occupancy"] or 0,
            "total_passengers": stats["total_passengers"] or 0,
            "peak_hour": peak_hour["hour"].isoformat() if peak_hour else None,
            "busiest_lines": [
                {
                    "line_id": line["line_id"],
                    "code": line["line__code"],
                    "name": line["line__name"],
                    "total_passengers": line["total"],
                }
                for line in busiest_lines
            ],
            "busiest_stops": [
                {
                    "stop_id": stop["stop_id"],
                    "name": stop["stop__name"],
                    "total_passengers": stop["total"],
                }
                for stop in busiest_stops
            ],
        }

    except Exception as e:
        logger.error(f"Error generating passenger report: {e}")
        return {}


def generate_bus_performance_report(report_date):
    """
    Generate bus performance report for a specific date.
    """
    try:
        # Define date range
        start_date = timezone.datetime.combine(report_date, timezone.time.min)
        end_date = timezone.datetime.combine(report_date, timezone.time.max)

        # Get trips
        from apps.tracking.models import Trip
        trips = Trip.objects.filter(
            start_time__gte=start_date,
            start_time__lte=end_date,
        )

        # Calculate statistics
        from django.db.models import Avg, Count, Max, Min, Sum

        total_trips = trips.count()

        if total_trips == 0:
            return {
                "date": report_date.isoformat(),
                "total_trips": 0,
                "total_distance": 0,
                "average_speed": 0,
                "average_trip_duration": 0,
                "total_passengers": 0,
                "most_active_buses": [],
            }

        stats = trips.aggregate(
            total_distance=Sum("distance"),
            avg_speed=Avg("average_speed"),
            total_passengers=Sum("max_passengers"),
        )

        # Calculate average trip duration
        completed_trips = trips.filter(
            is_completed=True,
            end_time__isnull=False,
        )

        avg_duration = None

        if completed_trips.exists():
            total_duration = timedelta()
            count = 0

            for trip in completed_trips:
                if trip.end_time and trip.start_time:
                    duration = trip.end_time - trip.start_time
                    total_duration += duration
                    count += 1

            if count > 0:
                avg_duration = total_duration.total_seconds() / count / 60  # minutes

        # Find most active buses
        most_active_buses = trips.values(
            "bus_id", "bus__license_plate"
        ).annotate(
            trip_count=Count("id"),
            total_distance=Sum("distance"),
            total_passengers=Sum("max_passengers"),
        ).order_by("-trip_count")[:10]

        return {
            "date": report_date.isoformat(),
            "total_trips": total_trips,
            "total_distance": stats["total_distance"] or 0,
            "average_speed": stats["avg_speed"] or 0,
            "average_trip_duration": avg_duration or 0,
            "total_passengers": stats["total_passengers"] or 0,
            "most_active_buses": [
                {
                    "bus_id": bus["bus_id"],
                    "license_plate": bus["bus__license_plate"],
                    "trip_count": bus["trip_count"],
                    "total_distance": bus["total_distance"] or 0,
                    "total_passengers": bus["total_passengers"] or 0,
                }
                for bus in most_active_buses
            ],
        }

    except Exception as e:
        logger.error(f"Error generating bus performance report: {e}")
        return {}


def generate_driver_performance_report(report_date):
    """
    Generate driver performance report for a specific date.
    """
    try:
        # Define date range
        start_date = timezone.datetime.combine(report_date, timezone.time.min)
        end_date = timezone.datetime.combine(report_date, timezone.time.max)

        # Get trips
        from apps.tracking.models import Trip
        trips = Trip.objects.filter(
            start_time__gte=start_date,
            start_time__lte=end_date,
        )

        # Calculate statistics
        from django.db.models import Avg, Count, Max, Min, Sum

        total_trips = trips.count()

        if total_trips == 0:
            return {
                "date": report_date.isoformat(),
                "total_trips": 0,
                "total_drivers": 0,
                "total_distance": 0,
                "top_drivers": [],
            }

        stats = trips.aggregate(
            total_distance=Sum("distance"),
            total_drivers=Count("driver_id", distinct=True),
        )

        # Get driver ratings for the day
        from apps.drivers.models import DriverRating
        ratings = DriverRating.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        )

        # Calculate average rating
        avg_rating = ratings.aggregate(avg=Avg("rating"))["avg"] or 0

        # Find top drivers
        top_drivers = trips.values(
            "driver_id",
            "driver__user__first_name",
            "driver__user__last_name",
            "driver__user__email",
        ).annotate(
            trip_count=Count("id"),
            total_distance=Sum("distance"),
            total_passengers=Sum("max_passengers"),
            avg_speed=Avg("average_speed"),
        ).order_by("-trip_count")[:10]

        # Get ratings for top drivers
        driver_ids = [driver["driver_id"] for driver in top_drivers]
        driver_ratings = {}

        for rating in ratings.filter(driver_id__in=driver_ids):
            driver_id = rating.driver_id
            if driver_id not in driver_ratings:
                driver_ratings[driver_id] = {
                    "count": 0,
                    "total": 0,
                }

            driver_ratings[driver_id]["count"] += 1
            driver_ratings[driver_id]["total"] += rating.rating

        return {
            "date": report_date.isoformat(),
            "total_trips": total_trips,
            "total_drivers": stats["total_drivers"] or 0,
            "total_distance": stats["total_distance"] or 0,
            "average_rating": avg_rating,
            "total_ratings": ratings.count(),
            "top_drivers": [
                {
                    "driver_id": driver["driver_id"],
                    "name": f"{driver['driver__user__first_name']} {driver['driver__user__last_name']}".strip() or
                            driver["driver__user__email"],
                    "trip_count": driver["trip_count"],
                    "total_distance": driver["total_distance"] or 0,
                    "total_passengers": driver["total_passengers"] or 0,
                    "average_speed": driver["avg_speed"] or 0,
                    "rating": (
                            driver_ratings.get(driver["driver_id"], {}).get("total", 0) /
                            driver_ratings.get(driver["driver_id"], {}).get("count", 1)
                    ) if driver["driver_id"] in driver_ratings else None,
                }
                for driver in top_drivers
            ],
        }

    except Exception as e:
        logger.error(f"Error generating driver performance report: {e}")
        return {}


def generate_line_performance_report(report_date):
    """
    Generate line performance report for a specific date.
    """
    try:
        # Define date range
        start_date = timezone.datetime.combine(report_date, timezone.time.min)
        end_date = timezone.datetime.combine(report_date, timezone.time.max)

        # Get trips
        from apps.tracking.models import Trip
        trips = Trip.objects.filter(
            start_time__gte=start_date,
            start_time__lte=end_date,
        )

        # Calculate statistics
        from django.db.models import Avg, Count, Max, Min, Sum

        total_trips = trips.count()

        if total_trips == 0:
            return {
                "date": report_date.isoformat(),
                "total_trips": 0,
                "total_lines": 0,
                "line_stats": [],
            }

        # Get line stats
        line_stats = trips.values(
            "line_id",
            "line__code",
            "line__name",
        ).annotate(
            trip_count=Count("id"),
            bus_count=Count("bus_id", distinct=True),
            driver_count=Count("driver_id", distinct=True),
            total_distance=Sum("distance"),
            total_passengers=Sum("max_passengers"),
            avg_speed=Avg("average_speed"),
        ).order_by("-trip_count")

        # Get anomalies by line
        from apps.tracking.models import Anomaly
        anomalies = Anomaly.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            trip__isnull=False,
        )

        line_anomalies = {}

        for anomaly in anomalies:
            line_id = anomaly.trip.line_id
            if line_id not in line_anomalies:
                line_anomalies[line_id] = 0

            line_anomalies[line_id] += 1

        return {
            "date": report_date.isoformat(),
            "total_trips": total_trips,
            "total_lines": line_stats.count(),
            "line_stats": [
                {
                    "line_id": line["line_id"],
                    "code": line["line__code"],
                    "name": line["line__name"],
                    "trip_count": line["trip_count"],
                    "bus_count": line["bus_count"],
                    "driver_count": line["driver_count"],
                    "total_distance": line["total_distance"] or 0,
                    "total_passengers": line["total_passengers"] or 0,
                    "average_speed": line["avg_speed"] or 0,
                    "anomalies": line_anomalies.get(line["line_id"], 0),
                }
                for line in line_stats
            ],
        }

    except Exception as e:
        logger.error(f"Error generating line performance report: {e}")
        return {}


def save_reports(report_date, passenger_report, bus_report, driver_report, line_report):
    """
    Save generated reports to database or file.
    """
    try:
        # Create a combined report
        combined_report = {
            "date": report_date.isoformat(),
            "passenger_report": passenger_report,
            "bus_report": bus_report,
            "driver_report": driver_report,
            "line_report": line_report,
        }

        # Save to database or file
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        import json

        # Convert to JSON
        report_json = json.dumps(combined_report, indent=2)

        # Save to file in media directory
        file_path = f"reports/{report_date.strftime('%Y-%m-%d')}_daily_report.json"
        default_storage.save(file_path, ContentFile(report_json.encode('utf-8')))

        logger.info(f"Saved daily reports to {file_path}")
        return True

    except Exception as e:
        logger.error(f"Error saving reports: {e}")
        return False