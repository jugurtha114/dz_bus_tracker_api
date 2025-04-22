from kombu import Exchange, Queue

# Define task queues
default_exchange = Exchange('default', type='direct')
tracking_exchange = Exchange('tracking', type='direct')
notification_exchange = Exchange('notification', type='direct')
eta_exchange = Exchange('eta', type='direct')

# Define task queues
task_queues = (
    Queue('default', default_exchange, routing_key='default'),
    Queue('tracking', tracking_exchange, routing_key='tracking'),
    Queue('notification', notification_exchange, routing_key='notification'),
    Queue('eta', eta_exchange, routing_key='eta'),
)

# Task routes - assign tasks to queues
CELERY_TASK_ROUTES = {
    # Tracking tasks
    'apps.tracking.tasks.*': {'queue': 'tracking'},
    
    # Notification tasks
    'apps.notifications.tasks.*': {'queue': 'notification'},
    
    # ETA tasks
    'apps.eta.tasks.*': {'queue': 'eta'},
    
    # Default
    '*': {'queue': 'default'},
}

# Task time limits
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 15 * 60  # 15 minutes

# Concurrency settings
CELERYD_CONCURRENCY = 8

# Optimization settings
CELERYD_PREFETCH_MULTIPLIER = 4
CELERY_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Rate limiting
CELERY_TASK_ANNOTATIONS = {
    'apps.tracking.tasks.process_location_updates': {'rate_limit': '100/m'},
    'apps.notifications.tasks.send_notification': {'rate_limit': '100/m'},
    'apps.eta.tasks.update_all_etas': {'rate_limit': '5/m'},
}

# Beat schedule
CELERY_BEAT_SCHEDULE = {
    'update_all_etas': {
        'task': 'apps.eta.tasks.update_all_etas',
        'schedule': 60.0,  # Every minute
    },
    'notify_eta_changes': {
        'task': 'apps.eta.tasks.notify_eta_changes',
        'schedule': 30.0,  # Every 30 seconds
    },
    'update_eta_statuses': {
        'task': 'apps.eta.tasks.update_eta_statuses',
        'schedule': 60.0,  # Every minute
    },
    'process_offline_batches': {
        'task': 'apps.tracking.tasks.process_offline_batches',
        'schedule': 120.0,  # Every 2 minutes
    },
    'cleanup_old_etas': {
        'task': 'apps.eta.tasks.cleanup_old_etas',
        'schedule': 3600.0,  # Every hour
    },
    'close_inactive_sessions': {
        'task': 'apps.tracking.tasks.close_inactive_sessions',
        'schedule': 300.0,  # Every 5 minutes
    },
    'mark_arrived_buses': {
        'task': 'apps.eta.tasks.mark_arrived_buses',
        'schedule': 20.0,  # Every 20 seconds
    },
    'generate_daily_analytics': {
        'task': 'apps.analytics.tasks.generate_daily_analytics',
        'schedule': 3600.0 * 24,  # Once a day
        'kwargs': {'days': 1},
    },
}
