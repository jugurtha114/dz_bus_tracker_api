"""
Service functions for the tracking app.
"""
import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Sum
from django.utils import timezone

from apps.buses.models import Bus
from apps.buses.selectors import get_bus_by_id
from apps.core.constants import BUS_TRACKING_STATUS_ACTIVE, BUS_TRACKING_STATUS_IDLE
from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object
from apps.core.utils.cache import (
    cache_bus_location,
    cache_bus_passengers,
    cache_line_buses,
    cache_stop_waiting,
)
from apps.core.utils.geo import calculate_distance
from apps.drivers.selectors import get_driver_by_id
from apps.lines.models import Line, Stop
from apps.lines.selectors import get_line_by_id, get_stop_by_id

from .models import (
    Anomaly,
    BusLine,
    LocationUpdate,
    PassengerCount,
    Trip,
    WaitingPassengers,
)
from .selectors import (
    get_active_trip,
    get_bus_line,
    get_latest_location_update,
    get_trip_by_id,
)

logger = logging.getLogger(__name__)


class BusLineService(BaseService):
    """
    Service for bus-line assignments.
    """

    @classmethod
    @transaction.atomic
    def assign_bus_to_line(cls, bus_id, line_id):
        """
        Assign a bus to a line.

        Args:
            bus_id: ID of the bus
            line_id: ID of the line

        Returns:
            Created BusLine object
        """
        try:
            # Get bus and line
            bus = get_bus_by_id(bus_id)
            line = get_line_by_id(line_id)

            # Check if already assigned
            if BusLine.objects.filter(bus=bus, line=line, is_active=True).exists():
                raise ValidationError("Bus is already assigned to this line.")

            # Create bus-line assignment
            bus_line = create_object(BusLine, {
                "bus": bus,
                "line": line,
                "is_active": True,
                "tracking_status": BUS_TRACKING_STATUS_IDLE,
            })

            logger.info(f"Assigned bus {bus.license_plate} to line {line.code}")
            return bus_line

        except Exception as e:
            logger.error(f"Error assigning bus to line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def unassign_bus_from_line(cls, bus_id, line_id):
        """
        Unassign a bus from a line.

        Args:
            bus_id: ID of the bus
            line_id: ID of the line

        Returns:
            Updated BusLine object
        """
        try:
            # Get bus-line assignment
            bus_line = get_bus_line(bus_id, line_id)

            # Update assignment
            bus_line.is_active = False
            bus_line.tracking_status = BUS_TRACKING_STATUS_IDLE
            bus_line.save(update_fields=["is_active", "tracking_status", "updated_at"])

            logger.info(
                f"Unassigned bus {bus_line.bus.license_plate} from line {bus_line.line.code}"
            )
            return bus_line

        except Exception as e:
            logger.error(f"Error unassigning bus from line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def start_tracking(cls, bus_id, line_id):
        """
        Start tracking a bus on a line.

        Args:
            bus_id: ID of the bus
            line_id: ID of the line

        Returns:
            Updated BusLine object and created Trip
        """
        try:
            # Get bus-line assignment
            bus_line = get_bus_line(bus_id, line_id)

            # Check if already tracking
            if bus_line.tracking_status == BUS_TRACKING_STATUS_ACTIVE:
                raise ValidationError("Bus is already tracking on this line.")

            # Get bus and line
            bus = bus_line.bus
            line = bus_line.line

            # Get driver
            driver = bus.driver

            # Generate trip ID
            trip_id = uuid.uuid4()

            # Create trip
            trip = create_object(Trip, {
                "bus": bus,
                "driver": driver,
                "line": line,
                "start_time": timezone.now(),
                "is_completed": False,
            })

            # Update bus-line assignment
            bus_line.tracking_status = BUS_TRACKING_STATUS_ACTIVE
            bus_line.trip_id = trip_id
            bus_line.start_time = trip.start_time
            bus_line.end_time = None
            bus_line.save(update_fields=[
                "tracking_status",
                "trip_id",
                "start_time",
                "end_time",
                "updated_at",
            ])

            logger.info(
                f"Started tracking bus {bus.license_plate} on line {line.code}"
            )
            return bus_line, trip

        except Exception as e:
            logger.error(f"Error starting tracking: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def stop_tracking(cls, bus_id, line_id):
        """
        Stop tracking a bus on a line.

        Args:
            bus_id: ID of the bus
            line_id: ID of the line

        Returns:
            Updated BusLine object and updated Trip
        """
        try:
            # Get bus-line assignment
            bus_line = get_bus_line(bus_id, line_id)

            # Check if tracking
            if bus_line.tracking_status != BUS_TRACKING_STATUS_ACTIVE:
                raise ValidationError("Bus is not tracking on this line.")

            # Get active trip
            trip = get_active_trip(bus_id)

            if not trip:
                raise ValidationError("No active trip found for this bus.")

            # Calculate trip statistics
            now = timezone.now()
            duration = now - trip.start_time

            # Get location updates for this trip
            location_updates = LocationUpdate.objects.filter(trip_id=trip.id)

            # Calculate distance
            total_distance = 0
            prev_update = None

            for update in location_updates.order_by("created_at"):
                if prev_update:
                    distance = calculate_distance(
                        float(prev_update.latitude),
                        float(prev_update.longitude),
                        float(update.latitude),
                        float(update.longitude)
                    )

                    if distance:
                        total_distance += distance

                prev_update = update

            # Calculate average speed
            average_speed = None
            if duration.total_seconds() > 0:
                average_speed = total_distance / (duration.total_seconds() / 3600)

            # Get maximum passengers
            max_passengers = PassengerCount.objects.filter(
                trip_id=trip.id
            ).aggregate(
                max=models.Max("count")
            )["max"] or 0

            # Count stops visited
            total_stops = location_updates.values("nearest_stop").distinct().count()

            # Update trip
            trip.end_time = now
            trip.is_completed = True
            trip.distance = total_distance
            trip.average_speed = average_speed
            trip.max_passengers = max_passengers
            trip.total_stops = total_stops
            trip.save(update_fields=[
                "end_time",
                "is_completed",
                "distance",
                "average_speed",
                "max_passengers",
                "total_stops",
                "updated_at",
            ])

            # Update bus-line assignment
            bus_line.tracking_status = BUS_TRACKING_STATUS_IDLE
            bus_line.end_time = now
            bus_line.save(update_fields=["tracking_status", "end_time", "updated_at"])

            logger.info(
                f"Stopped tracking bus {bus_line.bus.license_plate} on line {bus_line.line.code}"
            )
            return bus_line, trip

        except Exception as e:
            logger.error(f"Error stopping tracking: {e}")
            raise ValidationError(str(e))


class LocationUpdateService(BaseService):
    """
    Service for location updates.
    """

    @classmethod
    @transaction.atomic
    def record_location_update(cls, bus_id, latitude, longitude, **kwargs):
        """
        Record a location update for a bus.

        Args:
            bus_id: ID of the bus
            latitude: Latitude
            longitude: Longitude
            **kwargs: Additional location data

        Returns:
            Created LocationUpdate object
        """
        try:
            # Get bus
            bus = get_bus_by_id(bus_id)

            # Validate inputs
            if not latitude:
                raise ValidationError("Latitude is required.")

            if not longitude:
                raise ValidationError("Longitude is required.")

            # Get active trip
            trip = get_active_trip(bus_id)

            # Get line
            line = None
            if trip:
                line = trip.line

            # Create location data
            location_data = {
                "bus": bus,
                "latitude": latitude,
                "longitude": longitude,
                "trip_id": trip.id if trip else None,
                "line": line,
                **kwargs
            }

            # Find nearest stop if line is provided
            if line:
                from apps.lines.selectors import get_stops_by_line
                stops = get_stops_by_line(line.id)

                nearest_stop = None
                min_distance = float("inf")

                for stop in stops:
                    distance = calculate_distance(
                        float(latitude),
                        float(longitude),
                        float(stop.latitude),
                        float(stop.longitude)
                    )

                    if distance and distance < min_distance:
                        min_distance = distance
                        nearest_stop = stop

                if nearest_stop:
                    location_data["nearest_stop"] = nearest_stop
                    # Convert to meters
                    location_data["distance_to_stop"] = min_distance * 1000

            # Create location update
            location = create_object(LocationUpdate, location_data)

            # Update cache
            location_dict = {
                "id": str(location.id),
                "bus_id": str(bus.id),
                "latitude": float(location.latitude),
                "longitude": float(location.longitude),
                "altitude": float(location.altitude) if location.altitude else None,
                "speed": float(location.speed) if location.speed else None,
                "heading": float(location.heading) if location.heading else None,
                "accuracy": float(location.accuracy) if location.accuracy else None,
                "timestamp": location.created_at.isoformat(),
                "line_id": str(line.id) if line else None,
                "nearest_stop_id": str(location.nearest_stop_id) if location.nearest_stop_id else None,
                "distance_to_stop": float(location.distance_to_stop) if location.distance_to_stop else None,
            }

            cache_bus_location(bus.id, location_dict)

            # Update line buses cache if line exists
            if line:
                from .selectors import get_buses_on_line
                buses_on_line = get_buses_on_line(line.id)
                cache_line_buses(line.id, buses_on_line)

            logger.info(f"Recorded location update for bus {bus.license_plate}")
            return location

        except Exception as e:
            logger.error(f"Error recording location update: {e}")
            raise ValidationError(str(e))

    @classmethod
    def find_nearest_stop(cls, latitude, longitude, line_id=None, radius_km=0.5):
        """
        Find the nearest stop to a location.

        Args:
            latitude: Latitude
            longitude: Longitude
            line_id: Optional line ID to filter stops
            radius_km: Maximum radius in kilometers

        Returns:
            Nearest Stop object and distance in meters
        """
        try:
            # Get stops
            if line_id:
                from apps.lines.selectors import get_stops_by_line
                stops = get_stops_by_line(line_id)
            else:
                from apps.lines.selectors import get_active_stops
                stops = get_active_stops()

            nearest_stop = None
            min_distance = float("inf")

            for stop in stops:
                distance = calculate_distance(
                    float(latitude),
                    float(longitude),
                    float(stop.latitude),
                    float(stop.longitude)
                )

                if distance and distance < min_distance and distance <= radius_km:
                    min_distance = distance
                    nearest_stop = stop

            if nearest_stop:
                # Convert to meters
                return nearest_stop, min_distance * 1000

            return None, None

        except Exception as e:
            logger.error(f"Error finding nearest stop: {e}")
            return None, None


class PassengerCountService(BaseService):
    """
    Service for passenger counts.
    """

    @classmethod
    @transaction.atomic
    def update_passenger_count(cls, bus_id, count, **kwargs):
        """
        Update the passenger count for a bus.

        Args:
            bus_id: ID of the bus
            count: Number of passengers
            **kwargs: Additional passenger count data

        Returns:
            Created PassengerCount object
        """
        try:
            # Get bus
            bus = get_bus_by_id(bus_id)

            # Validate inputs
            if count < 0:
                raise ValidationError("Passenger count cannot be negative.")

            # Get active trip
            trip = get_active_trip(bus_id)

            # Get line
            line = None
            if trip:
                line = trip.line

            # Calculate occupancy rate
            occupancy_rate = min(count / bus.capacity, 1.0) if bus.capacity > 0 else 0

            # Create passenger count data
            passenger_data = {
                "bus": bus,
                "count": count,
                "capacity": bus.capacity,
                "occupancy_rate": occupancy_rate,
                "trip_id": trip.id if trip else None,
                "line": line,
                **kwargs
            }

            # Create passenger count
            passenger_count = create_object(PassengerCount, passenger_data)

            # Update cache
            cache_bus_passengers(bus.id, count)

            logger.info(f"Updated passenger count for bus {bus.license_plate}: {count}")
            return passenger_count

        except Exception as e:
            logger.error(f"Error updating passenger count: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_waiting_passengers(cls, stop_id, count, line_id=None, user_id=None):
        """
        Update the waiting passengers count at a stop.

        Args:
            stop_id: ID of the stop
            count: Number of waiting passengers
            line_id: Optional line ID
            user_id: Optional ID of the user reporting the count

        Returns:
            Created WaitingPassengers object
        """
        try:
            # Get stop
            stop = get_stop_by_id(stop_id)

            # Get line if provided
            line = None
            if line_id:
                line = get_line_by_id(line_id)

            # Validate inputs
            if count < 0:
                raise ValidationError("Waiting passengers count cannot be negative.")

            # Create waiting passengers data
            waiting_data = {
                "stop": stop,
                "count": count,
                "line": line,
            }

            # Add reporting user if provided
            if user_id:
                from apps.accounts.selectors import get_user_by_id
                waiting_data["reported_by"] = get_user_by_id(user_id)

            # Create waiting passengers
            waiting = create_object(WaitingPassengers, waiting_data)

            # Update cache
            cache_stop_waiting(stop.id, count)

            logger.info(f"Updated waiting passengers for stop {stop.name}: {count}")
            return waiting

        except Exception as e:
            logger.error(f"Error updating waiting passengers: {e}")
            raise ValidationError(str(e))


class TripService(BaseService):
    """
    Service for trips.
    """

    @classmethod
    @transaction.atomic
    def create_trip(cls, bus_id, driver_id, line_id, **kwargs):
        """
        Create a new trip.

        Args:
            bus_id: ID of the bus
            driver_id: ID of the driver
            line_id: ID of the line
            **kwargs: Additional trip data

        Returns:
            Created Trip object
        """
        try:
            # Get bus, driver, and line
            bus = get_bus_by_id(bus_id)
            driver = get_driver_by_id(driver_id)
            line = get_line_by_id(line_id)

            # Create trip data
            trip_data = {
                "bus": bus,
                "driver": driver,
                "line": line,
                "start_time": kwargs.get("start_time", timezone.now()),
                "is_completed": False,
                **kwargs
            }

            # Create trip
            trip = create_object(Trip, trip_data)

            logger.info(
                f"Created trip for bus {bus.license_plate} "
                f"with driver {driver.user.email} on line {line.code}"
            )
            return trip

        except Exception as e:
            logger.error(f"Error creating trip: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def end_trip(cls, trip_id, **kwargs):
        """
        End a trip.

        Args:
            trip_id: ID of the trip
            **kwargs: Additional trip data

        Returns:
            Updated Trip object
        """
        try:
            # Get trip
            trip = get_trip_by_id(trip_id)

            # Check if already completed
            if trip.is_completed:
                raise ValidationError("Trip is already completed.")

            # Update trip data
            trip_data = {
                "end_time": kwargs.get("end_time", timezone.now()),
                "is_completed": True,
                **kwargs
            }

            # Calculate statistics if not provided
            if "distance" not in trip_data:
                location_updates = LocationUpdate.objects.filter(trip_id=trip.id)

                total_distance = 0
                prev_update = None

                for update in location_updates.order_by("created_at"):
                    if prev_update:
                        distance = calculate_distance(
                            float(prev_update.latitude),
                            float(prev_update.longitude),
                            float(update.latitude),
                            float(update.longitude)
                        )

                        if distance:
                            total_distance += distance

                    prev_update = update

                trip_data["distance"] = total_distance

            if "average_speed" not in trip_data and trip_data.get("distance") and trip_data.get("end_time"):
                duration = (trip_data["end_time"] - trip.start_time).total_seconds() / 3600
                if duration > 0:
                    trip_data["average_speed"] = trip_data["distance"] / duration

            if "max_passengers" not in trip_data:
                max_passengers = PassengerCount.objects.filter(
                    trip_id=trip.id
                ).aggregate(
                    max=models.Max("count")
                )["max"] or 0

                trip_data["max_passengers"] = max_passengers

            if "total_stops" not in trip_data:
                total_stops = LocationUpdate.objects.filter(
                    trip_id=trip.id
                ).values("nearest_stop").distinct().count()

                trip_data["total_stops"] = total_stops

            # Update trip
            update_object(trip, trip_data)

            logger.info(f"Ended trip {trip.id}")
            return trip

        except Exception as e:
            logger.error(f"Error ending trip: {e}")
            raise ValidationError(str(e))


class AnomalyService(BaseService):
    """
    Service for anomalies.
    """

    @classmethod
    @transaction.atomic
    def create_anomaly(cls, bus_id, anomaly_type, description, **kwargs):
        """
        Create a new anomaly.

        Args:
            bus_id: ID of the bus
            anomaly_type: Type of anomaly
            description: Description of the anomaly
            **kwargs: Additional anomaly data

        Returns:
            Created Anomaly object
        """
        try:
            # Get bus
            bus = get_bus_by_id(bus_id)

            # Get active trip
            trip = get_active_trip(bus_id)

            # Validate inputs
            if not anomaly_type:
                raise ValidationError("Anomaly type is required.")

            if not description:
                raise ValidationError("Description is required.")

            # Create anomaly data
            anomaly_data = {
                "bus": bus,
                "trip": trip,
                "type": anomaly_type,
                "description": description,
                **kwargs
            }

            # Create anomaly
            anomaly = create_object(Anomaly, anomaly_data)

            logger.info(f"Created {anomaly_type} anomaly for bus {bus.license_plate}")
            return anomaly

        except Exception as e:
            logger.error(f"Error creating anomaly: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def resolve_anomaly(cls, anomaly_id, resolution_notes=None):
        """
        Resolve an anomaly.

        Args:
            anomaly_id: ID of the anomaly
            resolution_notes: Optional resolution notes

        Returns:
            Updated Anomaly object
        """
        try:
            # Get anomaly
            anomaly = get_object_or_404(Anomaly, id=anomaly_id)

            # Check if already resolved
            if anomaly.resolved:
                raise ValidationError("Anomaly is already resolved.")

            # Update anomaly
            anomaly.resolved = True
            anomaly.resolved_at = timezone.now()

            if resolution_notes:
                anomaly.resolution_notes = resolution_notes

            anomaly.save(update_fields=[
                "resolved",
                "resolved_at",
                "resolution_notes",
                "updated_at",
            ])

            logger.info(f"Resolved anomaly {anomaly.id}")
            return anomaly

        except Exception as e:
            logger.error(f"Error resolving anomaly: {e}")
            raise ValidationError(str(e))

    @classmethod
    def detect_speed_anomaly(cls, bus_id, speed, latitude, longitude):
        """
        Detect a speed anomaly for a bus.

        Args:
            bus_id: ID of the bus
            speed: Current speed
            latitude: Latitude
            longitude: Longitude

        Returns:
            Created Anomaly object or None
        """
        try:
            # Get bus
            bus = get_bus_by_id(bus_id)

            # Check speed
            if speed > 120:  # Example threshold, adjust as needed
                description = f"Speed anomaly detected: {speed} km/h"

                return cls.create_anomaly(
                    bus_id=bus_id,
                    anomaly_type="speed",
                    description=description,
                    severity="high",
                    location_latitude=latitude,
                    location_longitude=longitude,
                )

            return None

        except Exception as e:
            logger.error(f"Error detecting speed anomaly: {e}")
            return None

    @classmethod
    def detect_route_deviation(cls, bus_id, latitude, longitude, line_id):
        """
        Detect a route deviation for a bus.

        Args:
            bus_id: ID of the bus
            latitude: Latitude
            longitude: Longitude
            line_id: ID of the line

        Returns:
            Created Anomaly object or None
        """
        try:
            # Get nearest stop
            nearest_stop, distance = LocationUpdateService.find_nearest_stop(
                latitude, longitude, line_id, radius_km=1.0
            )

            # If no stop found within 1 km, might be off route
            if not nearest_stop:
                description = "Route deviation detected: No stops found within 1 km"

                return cls.create_anomaly(
                    bus_id=bus_id,
                    anomaly_type="route",
                    description=description,
                    severity="medium",
                    location_latitude=latitude,
                    location_longitude=longitude,
                )

            return None

        except Exception as e:
            logger.error(f"Error detecting route deviation: {e}")
            return None