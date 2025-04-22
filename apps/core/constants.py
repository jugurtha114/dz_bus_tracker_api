from django.utils.translation import gettext_lazy as _

# User types
USER_TYPE_ADMIN = 'admin'
USER_TYPE_DRIVER = 'driver'
USER_TYPE_PASSENGER = 'passenger'

USER_TYPES = (
    (USER_TYPE_ADMIN, _('Admin')),
    (USER_TYPE_DRIVER, _('Driver')),
    (USER_TYPE_PASSENGER, _('Passenger')),
)

# Application status
APPLICATION_STATUS_PENDING = 'pending'
APPLICATION_STATUS_APPROVED = 'approved'
APPLICATION_STATUS_REJECTED = 'rejected'

APPLICATION_STATUSES = (
    (APPLICATION_STATUS_PENDING, _('Pending')),
    (APPLICATION_STATUS_APPROVED, _('Approved')),
    (APPLICATION_STATUS_REJECTED, _('Rejected')),
)

# Tracking status
TRACKING_STATUS_ACTIVE = 'active'
TRACKING_STATUS_PAUSED = 'paused'
TRACKING_STATUS_COMPLETED = 'completed'
TRACKING_STATUS_ERROR = 'error'

TRACKING_STATUSES = (
    (TRACKING_STATUS_ACTIVE, _('Active')),
    (TRACKING_STATUS_PAUSED, _('Paused')),
    (TRACKING_STATUS_COMPLETED, _('Completed')),
    (TRACKING_STATUS_ERROR, _('Error')),
)

# Trip statuses
TRIP_STATUS_SCHEDULED = 'scheduled'
TRIP_STATUS_IN_PROGRESS = 'in_progress'
TRIP_STATUS_COMPLETED = 'completed'
TRIP_STATUS_CANCELLED = 'cancelled'
TRIP_STATUS_DELAYED = 'delayed'

TRIP_STATUSES = (
    (TRIP_STATUS_SCHEDULED, _('Scheduled')),
    (TRIP_STATUS_IN_PROGRESS, _('In Progress')),
    (TRIP_STATUS_COMPLETED, _('Completed')),
    (TRIP_STATUS_CANCELLED, _('Cancelled')),
    (TRIP_STATUS_DELAYED, _('Delayed')),
)

# ETA statuses
ETA_STATUS_SCHEDULED = 'scheduled'
ETA_STATUS_APPROACHING = 'approaching'
ETA_STATUS_ARRIVED = 'arrived'
ETA_STATUS_DELAYED = 'delayed'
ETA_STATUS_CANCELLED = 'cancelled'

ETA_STATUSES = (
    (ETA_STATUS_SCHEDULED, _('Scheduled')),
    (ETA_STATUS_APPROACHING, _('Approaching')),
    (ETA_STATUS_ARRIVED, _('Arrived')),
    (ETA_STATUS_DELAYED, _('Delayed')),
    (ETA_STATUS_CANCELLED, _('Cancelled')),
)

# Notification types
NOTIFICATION_TYPE_SYSTEM = 'system'
NOTIFICATION_TYPE_BUS_APPROACHING = 'bus_approaching'
NOTIFICATION_TYPE_DELAY = 'delay'
NOTIFICATION_TYPE_CANCELLATION = 'cancellation'
NOTIFICATION_TYPE_VERIFICATION = 'verification'
NOTIFICATION_TYPE_NEWS = 'news'

NOTIFICATION_TYPES = (
    (NOTIFICATION_TYPE_SYSTEM, _('System')),
    (NOTIFICATION_TYPE_BUS_APPROACHING, _('Bus Approaching')),
    (NOTIFICATION_TYPE_DELAY, _('Delay')),
    (NOTIFICATION_TYPE_CANCELLATION, _('Cancellation')),
    (NOTIFICATION_TYPE_VERIFICATION, _('Verification')),
    (NOTIFICATION_TYPE_NEWS, _('News')),
)

# Notification channels
NOTIFICATION_CHANNEL_PUSH = 'push'
NOTIFICATION_CHANNEL_SMS = 'sms'
NOTIFICATION_CHANNEL_EMAIL = 'email'
NOTIFICATION_CHANNEL_APP = 'app'

NOTIFICATION_CHANNELS = (
    (NOTIFICATION_CHANNEL_PUSH, _('Push')),
    (NOTIFICATION_CHANNEL_SMS, _('SMS')),
    (NOTIFICATION_CHANNEL_EMAIL, _('Email')),
    (NOTIFICATION_CHANNEL_APP, _('In-App')),
)

# Days of week
DAY_MONDAY = 0
DAY_TUESDAY = 1
DAY_WEDNESDAY = 2
DAY_THURSDAY = 3
DAY_FRIDAY = 4
DAY_SATURDAY = 5
DAY_SUNDAY = 6

DAYS_OF_WEEK = (
    (DAY_MONDAY, _('Monday')),
    (DAY_TUESDAY, _('Tuesday')),
    (DAY_WEDNESDAY, _('Wednesday')),
    (DAY_THURSDAY, _('Thursday')),
    (DAY_FRIDAY, _('Friday')),
    (DAY_SATURDAY, _('Saturday')),
    (DAY_SUNDAY, _('Sunday')),
)

# Feedback types
FEEDBACK_TYPE_GENERAL = 'general'
FEEDBACK_TYPE_BUG = 'bug'
FEEDBACK_TYPE_FEATURE = 'feature'
FEEDBACK_TYPE_COMPLAINT = 'complaint'
FEEDBACK_TYPE_PRAISE = 'praise'

FEEDBACK_TYPES = (
    (FEEDBACK_TYPE_GENERAL, _('General')),
    (FEEDBACK_TYPE_BUG, _('Bug')),
    (FEEDBACK_TYPE_FEATURE, _('Feature Request')),
    (FEEDBACK_TYPE_COMPLAINT, _('Complaint')),
    (FEEDBACK_TYPE_PRAISE, _('Praise')),
)

# Feedback status
FEEDBACK_STATUS_NEW = 'new'
FEEDBACK_STATUS_IN_PROGRESS = 'in_progress'
FEEDBACK_STATUS_RESOLVED = 'resolved'
FEEDBACK_STATUS_CLOSED = 'closed'

FEEDBACK_STATUSES = (
    (FEEDBACK_STATUS_NEW, _('New')),
    (FEEDBACK_STATUS_IN_PROGRESS, _('In Progress')),
    (FEEDBACK_STATUS_RESOLVED, _('Resolved')),
    (FEEDBACK_STATUS_CLOSED, _('Closed')),
)

# Abuse report reasons
ABUSE_REASON_HARASSMENT = 'harassment'
ABUSE_REASON_INAPPROPRIATE = 'inappropriate'
ABUSE_REASON_SPAM = 'spam'
ABUSE_REASON_FRAUD = 'fraud'
ABUSE_REASON_OTHER = 'other'

ABUSE_REASONS = (
    (ABUSE_REASON_HARASSMENT, _('Harassment')),
    (ABUSE_REASON_INAPPROPRIATE, _('Inappropriate Behavior')),
    (ABUSE_REASON_SPAM, _('Spam')),
    (ABUSE_REASON_FRAUD, _('Fraud')),
    (ABUSE_REASON_OTHER, _('Other')),
)

# Analytics period types
ANALYTICS_PERIOD_DAILY = 'daily'
ANALYTICS_PERIOD_WEEKLY = 'weekly'
ANALYTICS_PERIOD_MONTHLY = 'monthly'

ANALYTICS_PERIODS = (
    (ANALYTICS_PERIOD_DAILY, _('Daily')),
    (ANALYTICS_PERIOD_WEEKLY, _('Weekly')),
    (ANALYTICS_PERIOD_MONTHLY, _('Monthly')),
)

# Languages
LANGUAGE_FRENCH = 'fr'
LANGUAGE_ARABIC = 'ar'
LANGUAGE_ENGLISH = 'en'

LANGUAGES = (
    (LANGUAGE_FRENCH, _('French')),
    (LANGUAGE_ARABIC, _('Arabic')),
    (LANGUAGE_ENGLISH, _('English')),
)

# Cache keys
CACHE_KEY_LOCATION = 'location:{}'  # format with session_id
CACHE_KEY_ETA = 'eta:{}:{}:{}'  # format with line_id, stop_id, bus_id
CACHE_KEY_ACTIVE_BUSES = 'active_buses:{}'  # format with line_id
CACHE_KEY_LINE_STOPS = 'line_stops:{}'  # format with line_id
CACHE_KEY_BUS_SCHEDULE = 'bus_schedule:{}:{}'  # format with bus_id, date
CACHE_KEY_USER_FAVORITES = 'user_favorites:{}'  # format with user_id

# Default values
DEFAULT_LOCATION_UPDATE_INTERVAL = 20  # seconds
DEFAULT_ACCURACY_THRESHOLD = 50  # meters
DEFAULT_ETA_NOTIFICATION_THRESHOLD = 5  # minutes
DEFAULT_BUSES_PER_PAGE = 20
DEFAULT_CACHE_TIMEOUT = 300  # seconds

# Priority choices
PRIORITY_LOW = 'low'
PRIORITY_MEDIUM = 'medium'
PRIORITY_HIGH = 'high'
PRIORITY_URGENT = 'urgent'

PRIORITY_CHOICES = (
    (PRIORITY_LOW, _('Low')),
    (PRIORITY_MEDIUM, _('Medium')),
    (PRIORITY_HIGH, _('High')),
    (PRIORITY_URGENT, _('Urgent')),
)

# Support ticket categories
SUPPORT_TICKET_CATEGORY_ACCOUNT = 'account'
SUPPORT_TICKET_CATEGORY_TRACKING = 'tracking'
SUPPORT_TICKET_CATEGORY_APP = 'app'
SUPPORT_TICKET_CATEGORY_PAYMENT = 'payment'
SUPPORT_TICKET_CATEGORY_OTHER = 'other'

SUPPORT_TICKET_CATEGORIES = (
    (SUPPORT_TICKET_CATEGORY_ACCOUNT, _('Account')),
    (SUPPORT_TICKET_CATEGORY_TRACKING, _('Tracking')),
    (SUPPORT_TICKET_CATEGORY_APP, _('App')),
    (SUPPORT_TICKET_CATEGORY_PAYMENT, _('Payment')),
    (SUPPORT_TICKET_CATEGORY_OTHER, _('Other')),
)


# from django.utils.translation import gettext_lazy as _
#
# # User types
# USER_TYPE_ADMIN = 'admin'
# USER_TYPE_DRIVER = 'driver'
# USER_TYPE_PASSENGER = 'passenger'
#
# USER_TYPES = (
#     (USER_TYPE_ADMIN, _('Admin')),
#     (USER_TYPE_DRIVER, _('Driver')),
#     (USER_TYPE_PASSENGER, _('Passenger')),
# )
#
# # Application status
# APPLICATION_STATUS_PENDING = 'pending'
# APPLICATION_STATUS_APPROVED = 'approved'
# APPLICATION_STATUS_REJECTED = 'rejected'
#
# APPLICATION_STATUSES = (
#     (APPLICATION_STATUS_PENDING, _('Pending')),
#     (APPLICATION_STATUS_APPROVED, _('Approved')),
#     (APPLICATION_STATUS_REJECTED, _('Rejected')),
# )
#
# # Tracking status
# TRACKING_STATUS_ACTIVE = 'active'
# TRACKING_STATUS_PAUSED = 'paused'
# TRACKING_STATUS_COMPLETED = 'completed'
# TRACKING_STATUS_ERROR = 'error'
#
# TRACKING_STATUSES = (
#     (TRACKING_STATUS_ACTIVE, _('Active')),
#     (TRACKING_STATUS_PAUSED, _('Paused')),
#     (TRACKING_STATUS_COMPLETED, _('Completed')),
#     (TRACKING_STATUS_ERROR, _('Error')),
# )
#
# # Trip statuses
# TRIP_STATUS_SCHEDULED = 'scheduled'
# TRIP_STATUS_IN_PROGRESS = 'in_progress'
# TRIP_STATUS_COMPLETED = 'completed'
# TRIP_STATUS_CANCELLED = 'cancelled'
# TRIP_STATUS_DELAYED = 'delayed'
#
# TRIP_STATUSES = (
#     (TRIP_STATUS_SCHEDULED, _('Scheduled')),
#     (TRIP_STATUS_IN_PROGRESS, _('In Progress')),
#     (TRIP_STATUS_COMPLETED, _('Completed')),
#     (TRIP_STATUS_CANCELLED, _('Cancelled')),
#     (TRIP_STATUS_DELAYED, _('Delayed')),
# )
#
# # ETA statuses
# ETA_STATUS_SCHEDULED = 'scheduled'
# ETA_STATUS_APPROACHING = 'approaching'
# ETA_STATUS_ARRIVED = 'arrived'
# ETA_STATUS_DELAYED = 'delayed'
# ETA_STATUS_CANCELLED = 'cancelled'
#
# ETA_STATUSES = (
#     (ETA_STATUS_SCHEDULED, _('Scheduled')),
#     (ETA_STATUS_APPROACHING, _('Approaching')),
#     (ETA_STATUS_ARRIVED, _('Arrived')),
#     (ETA_STATUS_DELAYED, _('Delayed')),
#     (ETA_STATUS_CANCELLED, _('Cancelled')),
# )
#
# # Notification types
# NOTIFICATION_TYPE_SYSTEM = 'system'
# NOTIFICATION_TYPE_BUS_APPROACHING = 'bus_approaching'
# NOTIFICATION_TYPE_DELAY = 'delay'
# NOTIFICATION_TYPE_CANCELLATION = 'cancellation'
# NOTIFICATION_TYPE_VERIFICATION = 'verification'
# NOTIFICATION_TYPE_NEWS = 'news'
#
# NOTIFICATION_TYPES = (
#     (NOTIFICATION_TYPE_SYSTEM, _('System')),
#     (NOTIFICATION_TYPE_BUS_APPROACHING, _('Bus Approaching')),
#     (NOTIFICATION_TYPE_DELAY, _('Delay')),
#     (NOTIFICATION_TYPE_CANCELLATION, _('Cancellation')),
#     (NOTIFICATION_TYPE_VERIFICATION, _('Verification')),
#     (NOTIFICATION_TYPE_NEWS, _('News')),
# )
#
# # Notification channels
# NOTIFICATION_CHANNEL_PUSH = 'push'
# NOTIFICATION_CHANNEL_SMS = 'sms'
# NOTIFICATION_CHANNEL_EMAIL = 'email'
# NOTIFICATION_CHANNEL_APP = 'app'
#
# NOTIFICATION_CHANNELS = (
#     (NOTIFICATION_CHANNEL_PUSH, _('Push')),
#     (NOTIFICATION_CHANNEL_SMS, _('SMS')),
#     (NOTIFICATION_CHANNEL_EMAIL, _('Email')),
#     (NOTIFICATION_CHANNEL_APP, _('In-App')),
# )
#
# # Days of week
# DAY_MONDAY = 0
# DAY_TUESDAY = 1
# DAY_WEDNESDAY = 2
# DAY_THURSDAY = 3
# DAY_FRIDAY = 4
# DAY_SATURDAY = 5
# DAY_SUNDAY = 6
#
# DAYS_OF_WEEK = (
#     (DAY_MONDAY, _('Monday')),
#     (DAY_TUESDAY, _('Tuesday')),
#     (DAY_WEDNESDAY, _('Wednesday')),
#     (DAY_THURSDAY, _('Thursday')),
#     (DAY_FRIDAY, _('Friday')),
#     (DAY_SATURDAY, _('Saturday')),
#     (DAY_SUNDAY, _('Sunday')),
# )
#
# # Feedback types
# FEEDBACK_TYPE_GENERAL = 'general'
# FEEDBACK_TYPE_BUG = 'bug'
# FEEDBACK_TYPE_FEATURE = 'feature'
# FEEDBACK_TYPE_COMPLAINT = 'complaint'
# FEEDBACK_TYPE_PRAISE = 'praise'
#
# FEEDBACK_TYPES = (
#     (FEEDBACK_TYPE_GENERAL, _('General')),
#     (FEEDBACK_TYPE_BUG, _('Bug')),
#     (FEEDBACK_TYPE_FEATURE, _('Feature Request')),
#     (FEEDBACK_TYPE_COMPLAINT, _('Complaint')),
#     (FEEDBACK_TYPE_PRAISE, _('Praise')),
# )
#
# # Feedback status
# FEEDBACK_STATUS_NEW = 'new'
# FEEDBACK_STATUS_IN_PROGRESS = 'in_progress'
# FEEDBACK_STATUS_RESOLVED = 'resolved'
# FEEDBACK_STATUS_CLOSED = 'closed'
#
# FEEDBACK_STATUSES = (
#     (FEEDBACK_STATUS_NEW, _('New')),
#     (FEEDBACK_STATUS_IN_PROGRESS, _('In Progress')),
#     (FEEDBACK_STATUS_RESOLVED, _('Resolved')),
#     (FEEDBACK_STATUS_CLOSED, _('Closed')),
# )
#
# # Abuse report reasons
# ABUSE_REASON_HARASSMENT = 'harassment'
# ABUSE_REASON_INAPPROPRIATE = 'inappropriate'
# ABUSE_REASON_SPAM = 'spam'
# ABUSE_REASON_FRAUD = 'fraud'
# ABUSE_REASON_OTHER = 'other'
#
# ABUSE_REASONS = (
#     (ABUSE_REASON_HARASSMENT, _('Harassment')),
#     (ABUSE_REASON_INAPPROPRIATE, _('Inappropriate Behavior')),
#     (ABUSE_REASON_SPAM, _('Spam')),
#     (ABUSE_REASON_FRAUD, _('Fraud')),
#     (ABUSE_REASON_OTHER, _('Other')),
# )
#
# # Analytics period types
# ANALYTICS_PERIOD_DAILY = 'daily'
# ANALYTICS_PERIOD_WEEKLY = 'weekly'
# ANALYTICS_PERIOD_MONTHLY = 'monthly'
#
# ANALYTICS_PERIODS = (
#     (ANALYTICS_PERIOD_DAILY, _('Daily')),
#     (ANALYTICS_PERIOD_WEEKLY, _('Weekly')),
#     (ANALYTICS_PERIOD_MONTHLY, _('Monthly')),
# )
#
# # Languages
# LANGUAGE_FRENCH = 'fr'
# LANGUAGE_ARABIC = 'ar'
# LANGUAGE_ENGLISH = 'en'
#
# LANGUAGES = (
#     (LANGUAGE_FRENCH, _('French')),
#     (LANGUAGE_ARABIC, _('Arabic')),
#     (LANGUAGE_ENGLISH, _('English')),
# )
#
# # Cache keys
# CACHE_KEY_LOCATION = 'location:{}'  # format with session_id
# CACHE_KEY_ETA = 'eta:{}:{}:{}' # format with line_id, stop_id, bus_id
# CACHE_KEY_ACTIVE_BUSES = 'active_buses:{}' # format with line_id
# CACHE_KEY_LINE_STOPS = 'line_stops:{}' # format with line_id
# CACHE_KEY_BUS_SCHEDULE = 'bus_schedule:{}:{}' # format with bus_id, date
# CACHE_KEY_USER_FAVORITES = 'user_favorites:{}' # format with user_id
#
# # Default values
# DEFAULT_LOCATION_UPDATE_INTERVAL = 20  # seconds
# DEFAULT_ACCURACY_THRESHOLD = 50  # meters
# DEFAULT_ETA_NOTIFICATION_THRESHOLD = 5  # minutes
# DEFAULT_BUSES_PER_PAGE = 20
# DEFAULT_CACHE_TIMEOUT = 300  # seconds
