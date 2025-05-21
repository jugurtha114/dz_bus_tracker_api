"""
Service functions for the lines app.
"""
import logging
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ValidationError
from apps.core.services import BaseService, create_object, update_object
from apps.core.utils.geo import calculate_distance

from .models import Line, LineStop, Schedule, Stop
from .selectors import get_line_by_id, get_stop_by_id

logger = logging.getLogger(__name__)


class StopService(BaseService):
    """
    Service for stop-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_stop(cls, name, latitude, longitude, **kwargs):
        """
        Create a new stop.

        Args:
            name: Name of the stop
            latitude: Latitude of the stop
            longitude: Longitude of the stop
            **kwargs: Additional stop data

        Returns:
            Created stop
        """
        try:
            # Validate inputs
            if not name:
                raise ValidationError("Name is required.")

            if not latitude:
                raise ValidationError("Latitude is required.")

            if not longitude:
                raise ValidationError("Longitude is required.")

            # Create stop
            stop_data = {
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                **kwargs
            }

            stop = create_object(Stop, stop_data)

            logger.info(f"Created new stop: {stop.name}")
            return stop

        except Exception as e:
            logger.error(f"Error creating stop: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_stop(cls, stop_id, **data):
        """
        Update a stop.

        Args:
            stop_id: ID of the stop to update
            **data: Stop data to update

        Returns:
            Updated stop
        """
        stop = get_stop_by_id(stop_id)

        try:
            update_object(stop, data)
            logger.info(f"Updated stop: {stop.name}")
            return stop

        except Exception as e:
            logger.error(f"Error updating stop: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def deactivate_stop(cls, stop_id):
        """
        Deactivate a stop.

        Args:
            stop_id: ID of the stop to deactivate

        Returns:
            Deactivated stop
        """
        stop = get_stop_by_id(stop_id)

        try:
            stop.is_active = False
            stop.save(update_fields=["is_active", "updated_at"])

            logger.info(f"Deactivated stop: {stop.name}")
            return stop

        except Exception as e:
            logger.error(f"Error deactivating stop: {e}")
            raise ValidationError(str(e))


class LineService(BaseService):
    """
    Service for line-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_line(cls, name, code, **kwargs):
        """
        Create a new line.

        Args:
            name: Name of the line
            code: Code of the line
            **kwargs: Additional line data

        Returns:
            Created line
        """
        try:
            # Validate inputs
            if not name:
                raise ValidationError("Name is required.")

            if not code:
                raise ValidationError("Code is required.")

            # Create line
            line_data = {
                "name": name,
                "code": code,
                **kwargs
            }

            line = create_object(Line, line_data)

            logger.info(f"Created new line: {line.code} - {line.name}")
            return line

        except Exception as e:
            logger.error(f"Error creating line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_line(cls, line_id, **data):
        """
        Update a line.

        Args:
            line_id: ID of the line to update
            **data: Line data to update

        Returns:
            Updated line
        """
        line = get_line_by_id(line_id)

        # Don't allow updating code
        data.pop("code", None)

        try:
            update_object(line, data)
            logger.info(f"Updated line: {line.code} - {line.name}")
            return line

        except Exception as e:
            logger.error(f"Error updating line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def deactivate_line(cls, line_id):
        """
        Deactivate a line.

        Args:
            line_id: ID of the line to deactivate

        Returns:
            Deactivated line
        """
        line = get_line_by_id(line_id)

        try:
            line.is_active = False
            line.save(update_fields=["is_active", "updated_at"])

            logger.info(f"Deactivated line: {line.code} - {line.name}")
            return line

        except Exception as e:
            logger.error(f"Error deactivating line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def add_stop_to_line(cls, line_id, stop_id, order, **kwargs):
        """
        Add a stop to a line.

        Args:
            line_id: ID of the line
            stop_id: ID of the stop
            order: Order of the stop in the line
            **kwargs: Additional line-stop data

        Returns:
            Created LineStop
        """
        try:
            # Get line and stop
            line = get_line_by_id(line_id)
            stop = get_stop_by_id(stop_id)

            # Check if already exists
            if LineStop.objects.filter(line=line, stop=stop).exists():
                raise ValidationError("This stop is already in this line.")

            # Check if order is already taken
            if LineStop.objects.filter(line=line, order=order).exists():
                raise ValidationError("This order is already taken in this line.")

            # Create line-stop relationship
            line_stop_data = {
                "line": line,
                "stop": stop,
                "order": order,
                **kwargs
            }

            # Automatically calculate distance from previous
            if order > 0 and "distance_from_previous" not in kwargs:
                try:
                    prev_line_stop = LineStop.objects.get(line=line, order=order - 1)
                    prev_stop = prev_line_stop.stop

                    distance = calculate_distance(
                        float(prev_stop.latitude),
                        float(prev_stop.longitude),
                        float(stop.latitude),
                        float(stop.longitude)
                    )

                    if distance:
                        # Convert to meters
                        line_stop_data["distance_from_previous"] = distance * 1000
                except LineStop.DoesNotExist:
                    pass

            line_stop = create_object(LineStop, line_stop_data)

            logger.info(f"Added stop {stop.name} to line {line.code} at position {order}")
            return line_stop

        except Exception as e:
            logger.error(f"Error adding stop to line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def remove_stop_from_line(cls, line_id, stop_id):
        """
        Remove a stop from a line.

        Args:
            line_id: ID of the line
            stop_id: ID of the stop

        Returns:
            True if successful
        """
        try:
            # Get line and stop
            line = get_line_by_id(line_id)
            stop = get_stop_by_id(stop_id)

            # Get line-stop relationship
            line_stop = LineStop.objects.get(line=line, stop=stop)

            # Get order
            order = line_stop.order

            # Delete line-stop relationship
            line_stop.delete()

            # Update subsequent orders
            LineStop.objects.filter(
                line=line,
                order__gt=order
            ).update(
                order=F("order") - 1
            )

            logger.info(f"Removed stop {stop.name} from line {line.code}")
            return True

        except LineStop.DoesNotExist:
            raise ValidationError("This stop is not in this line.")

        except Exception as e:
            logger.error(f"Error removing stop from line: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_line_stop_order(cls, line_id, stop_id, new_order):
        """
        Update the order of a stop in a line.

        Args:
            line_id: ID of the line
            stop_id: ID of the stop
            new_order: New order of the stop

        Returns:
            Updated LineStop
        """
        try:
            # Get line and stop
            line = get_line_by_id(line_id)
            stop = get_stop_by_id(stop_id)

            # Get line-stop relationship
            line_stop = LineStop.objects.get(line=line, stop=stop)

            # Get current order
            current_order = line_stop.order

            # If new order is the same as current order, do nothing
            if new_order == current_order:
                return line_stop

            # Check if new order is valid
            max_order = LineStop.objects.filter(line=line).count() - 1
            if new_order < 0 or new_order > max_order:
                raise ValidationError(f"Order must be between 0 and {max_order}.")

            # Update orders
            if new_order > current_order:
                # Moving down, shift stops in between up
                LineStop.objects.filter(
                    line=line,
                    order__gt=current_order,
                    order__lte=new_order
                ).update(
                    order=F("order") - 1
                )
            else:
                # Moving up, shift stops in between down
                LineStop.objects.filter(
                    line=line,
                    order__gte=new_order,
                    order__lt=current_order
                ).update(
                    order=F("order") + 1
                )

            # Update the stop order
            line_stop.order = new_order
            line_stop.save(update_fields=["order", "updated_at"])

            logger.info(
                f"Updated order of stop {stop.name} in line {line.code} "
                f"from {current_order} to {new_order}"
            )
            return line_stop

        except LineStop.DoesNotExist:
            raise ValidationError("This stop is not in this line.")

        except Exception as e:
            logger.error(f"Error updating line stop order: {e}")
            raise ValidationError(str(e))


class ScheduleService(BaseService):
    """
    Service for schedule-related operations.
    """

    @classmethod
    @transaction.atomic
    def create_schedule(cls, line_id, day_of_week, start_time, end_time, frequency_minutes, **kwargs):
        """
        Create a new schedule for a line.

        Args:
            line_id: ID of the line
            day_of_week: Day of week (0-6, where 0 is Monday)
            start_time: Start time
            end_time: End time
            frequency_minutes: Frequency in minutes
            **kwargs: Additional schedule data

        Returns:
            Created schedule
        """
        try:
            # Get line
            line = get_line_by_id(line_id)

            # Validate inputs
            if day_of_week < 0 or day_of_week > 6:
                raise ValidationError("Day of week must be between 0 and 6.")

            if start_time >= end_time:
                raise ValidationError("Start time must be before end time.")

            if frequency_minutes <= 0:
                raise ValidationError("Frequency must be greater than zero.")

            # Check for overlap
            if Schedule.objects.filter(
                    line=line,
                    day_of_week=day_of_week,
                    start_time__lt=end_time,
                    end_time__gt=start_time
            ).exists():
                raise ValidationError("This schedule overlaps with an existing schedule.")

            # Create schedule
            schedule_data = {
                "line": line,
                "day_of_week": day_of_week,
                "start_time": start_time,
                "end_time": end_time,
                "frequency_minutes": frequency_minutes,
                **kwargs
            }

            schedule = create_object(Schedule, schedule_data)

            logger.info(f"Created new schedule for line {line.code} on day {day_of_week}")
            return schedule

        except Exception as e:
            logger.error(f"Error creating schedule: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def update_schedule(cls, schedule_id, **data):
        """
        Update a schedule.

        Args:
            schedule_id: ID of the schedule to update
            **data: Schedule data to update

        Returns:
            Updated schedule
        """
        try:
            # Get schedule
            schedule = Schedule.objects.get(id=schedule_id)

            # Check for overlap if changing times or day
            changes_time = "start_time" in data or "end_time" in data or "day_of_week" in data

            if changes_time:
                day_of_week = data.get("day_of_week", schedule.day_of_week)
                start_time = data.get("start_time", schedule.start_time)
                end_time = data.get("end_time", schedule.end_time)

                if start_time >= end_time:
                    raise ValidationError("Start time must be before end time.")

                # Check for overlap with other schedules
                overlapping = Schedule.objects.filter(
                    line=schedule.line,
                    day_of_week=day_of_week,
                    start_time__lt=end_time,
                    end_time__gt=start_time
                ).exclude(id=schedule.id)

                if overlapping.exists():
                    raise ValidationError("This schedule would overlap with an existing schedule.")

            update_object(schedule, data)
            logger.info(f"Updated schedule for line {schedule.line.code} on day {schedule.day_of_week}")
            return schedule

        except Schedule.DoesNotExist:
            raise ValidationError("Schedule not found.")

        except Exception as e:
            logger.error(f"Error updating schedule: {e}")
            raise ValidationError(str(e))

    @classmethod
    @transaction.atomic
    def delete_schedule(cls, schedule_id):
        """
        Delete a schedule.

        Args:
            schedule_id: ID of the schedule to delete

        Returns:
            True if successful
        """
        try:
            # Get schedule
            schedule = Schedule.objects.get(id=schedule_id)

            # Delete schedule
            schedule.delete()

            logger.info(f"Deleted schedule for line {schedule.line.code} on day {schedule.day_of_week}")
            return True

        except Schedule.DoesNotExist:
            raise ValidationError("Schedule not found.")

        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            raise ValidationError(str(e))