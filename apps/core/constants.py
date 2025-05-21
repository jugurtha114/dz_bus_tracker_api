"""
Constants used throughout the DZ Bus Tracker application.
"""
from django.utils.translation import gettext_lazy as _

# Language choices
LANGUAGE_CHOICES = (
    ("fr", _("French")),
    ("ar", _("Arabic")),
    ("en", _("English")),
)

# User types
USER_TYPE_ADMIN = "admin"
USER_TYPE_DRIVER = "driver"
USER_TYPE_PASSENGER = "passenger"

USER_TYPE_CHOICES = (
    (USER_TYPE_ADMIN, _("Admin")),
    (USER_TYPE_DRIVER, _("Driver")),
    (USER_TYPE_PASSENGER, _("Passenger")),
)

# Driver status
DRIVER_STATUS_PENDING = "pending"
DRIVER_STATUS_APPROVED = "approved"
DRIVER_STATUS_REJECTED = "rejected"
DRIVER_STATUS_SUSPENDED = "suspended"

DRIVER_STATUS_CHOICES = (
    (DRIVER_STATUS_PENDING, _("Pending")),
    (DRIVER_STATUS_APPROVED, _("Approved")),
    (DRIVER_STATUS_REJECTED, _("Rejected")),
    (DRIVER_STATUS_SUSPENDED, _("Suspended")),
)

# Bus status
BUS_STATUS_ACTIVE = "active"
BUS_STATUS_INACTIVE = "inactive"
BUS_STATUS_MAINTENANCE = "maintenance"

BUS_STATUS_CHOICES = (
    (BUS_STATUS_ACTIVE, _("Active")),
    (BUS_STATUS_INACTIVE, _("Inactive")),
    (BUS_STATUS_MAINTENANCE, _("Maintenance")),
)

# Bus tracking status
BUS_TRACKING_STATUS_IDLE = "idle"
BUS_TRACKING_STATUS_ACTIVE = "active"
BUS_TRACKING_STATUS_PAUSED = "paused"

BUS_TRACKING_STATUS_CHOICES = (
    (BUS_TRACKING_STATUS_IDLE, _("Idle")),
    (BUS_TRACKING_STATUS_ACTIVE, _("Active")),
    (BUS_TRACKING_STATUS_PAUSED, _("Paused")),
)

# Rating choices (1-5 stars)
RATING_CHOICES = tuple((i, str(i)) for i in range(1, 6))

# Notification types
NOTIFICATION_TYPE_DRIVER_APPROVED = "driver_approved"
NOTIFICATION_TYPE_DRIVER_REJECTED = "driver_rejected"
NOTIFICATION_TYPE_BUS_ARRIVING = "bus_arriving"
NOTIFICATION_TYPE_BUS_DELAYED = "bus_delayed"
NOTIFICATION_TYPE_BUS_CANCELLED = "bus_cancelled"
NOTIFICATION_TYPE_SYSTEM = "system"

NOTIFICATION_TYPE_CHOICES = (
    (NOTIFICATION_TYPE_DRIVER_APPROVED, _("Driver Approved")),
    (NOTIFICATION_TYPE_DRIVER_REJECTED, _("Driver Rejected")),
    (NOTIFICATION_TYPE_BUS_ARRIVING, _("Bus Arriving")),
    (NOTIFICATION_TYPE_BUS_DELAYED, _("Bus Delayed")),
    (NOTIFICATION_TYPE_BUS_CANCELLED, _("Bus Cancelled")),
    (NOTIFICATION_TYPE_SYSTEM, _("System")),
)

# Notification channels
NOTIFICATION_CHANNEL_PUSH = "push"
NOTIFICATION_CHANNEL_SMS = "sms"
NOTIFICATION_CHANNEL_EMAIL = "email"
NOTIFICATION_CHANNEL_IN_APP = "in_app"

NOTIFICATION_CHANNEL_CHOICES = (
    (NOTIFICATION_CHANNEL_PUSH, _("Push")),
    (NOTIFICATION_CHANNEL_SMS, _("SMS")),
    (NOTIFICATION_CHANNEL_EMAIL, _("Email")),
    (NOTIFICATION_CHANNEL_IN_APP, _("In App")),
)

# Day of week choices
MONDAY = 0
TUESDAY = 1
WEDNESDAY = 2
THURSDAY = 3
FRIDAY = 4
SATURDAY = 5
SUNDAY = 6

DAY_OF_WEEK_CHOICES = (
    (MONDAY, _("Monday")),
    (TUESDAY, _("Tuesday")),
    (WEDNESDAY, _("Wednesday")),
    (THURSDAY, _("Thursday")),
    (FRIDAY, _("Friday")),
    (SATURDAY, _("Saturday")),
    (SUNDAY, _("Sunday")),
)

# Cache keys
CACHE_KEY_BUS_LOCATION = "bus:location:{bus_id}"
CACHE_KEY_BUS_PASSENGERS = "bus:passengers:{bus_id}"
CACHE_KEY_STOP_WAITING = "stop:waiting:{stop_id}"
CACHE_KEY_LINE_BUSES = "line:buses:{line_id}"
CACHE_KEY_DRIVER_RATING = "driver:rating:{driver_id}"

# Cache timeouts (in seconds)
CACHE_TIMEOUT_BUS_LOCATION = 60  # 1 minute
CACHE_TIMEOUT_BUS_PASSENGERS = 300  # 5 minutes
CACHE_TIMEOUT_STOP_WAITING = 300  # 5 minutes
CACHE_TIMEOUT_LINE_BUSES = 300  # 5 minutes
CACHE_TIMEOUT_DRIVER_RATING = 3600  # 1 hour
