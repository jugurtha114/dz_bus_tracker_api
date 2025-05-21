"""
Storage backends for DZ Bus Tracker.
"""
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    """
    Storage for static files on S3.
    """
    location = "static"
    default_acl = "public-read"


class MediaStorage(S3Boto3Storage):
    """
    Storage for media files on S3, including driver and bus photos.
    """
    location = "media"
    file_overwrite = False
    default_acl = "public-read"


class PrivateMediaStorage(S3Boto3Storage):
    """
    Storage for private media files on S3, like driver ID photos.
    """
    location = "private"
    default_acl = "private"
    file_overwrite = False
    custom_domain = False
    