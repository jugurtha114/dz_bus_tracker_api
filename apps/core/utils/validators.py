"""
Custom validators for DZ Bus Tracker.
"""
import re
from datetime import date

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_phone_number(value):
    """
    Validate an Algerian phone number.

    Valid formats:
    - +213XXXXXXXXX
    - 00213XXXXXXXXX
    - 0XXXXXXXXX
    """
    algerian_phone_regex = r"^(?:(?:\+|00)213|0)(?:5|6|7)[0-9]{8}$"
    if not re.match(algerian_phone_regex, value):
        raise ValidationError(
            _("Enter a valid Algerian phone number."), code="invalid_phone_number"
        )


def validate_plate_number(value):
    """
    Validate an Algerian license plate number.

    Valid format: 12345-678-09 (wilaya-sequence-check digits)
    """
    algerian_plate_regex = r"^\d{1,5}-\d{3}-\d{2}$"
    if not re.match(algerian_plate_regex, value):
        raise ValidationError(
            _("Enter a valid Algerian license plate number (e.g., 12345-678-09)."),
            code="invalid_plate_number",
        )


def validate_id_card_number(value):
    """
    Validate an Algerian national ID card number.
    """
    if not re.match(r"^\d{18}$", value):
        raise ValidationError(
            _("Enter a valid Algerian national ID card number (18 digits)."),
            code="invalid_id_card_number",
        )


def validate_future_date(value):
    """
    Validate that a date is in the future.
    """
    if value < date.today():
        raise ValidationError(
            _("Date must be in the future."), code="date_not_in_future"
        )


def validate_past_date(value):
    """
    Validate that a date is in the past.
    """
    if value > date.today():
        raise ValidationError(
            _("Date must be in the past."), code="date_not_in_past"
        )


def validate_file_size(value, max_size=5242880):  # 5MB default
    """
    Validate that a file is not too large.
    """
    if value.size > max_size:
        raise ValidationError(
            _("File size must not exceed %(max_size)s MB."),
            params={"max_size": max_size / 1024 / 1024},
            code="file_too_large",
        )


def validate_image_dimensions(value, min_width=100, min_height=100, max_width=4000, max_height=4000):
    """
    Validate image dimensions.
    """
    from PIL import Image

    image = Image.open(value)
    width, height = image.size

    if width < min_width or height < min_height:
        raise ValidationError(
            _("Image dimensions must be at least %(min_width)s x %(min_height)s pixels."),
            params={"min_width": min_width, "min_height": min_height},
            code="image_too_small",
        )

    if width > max_width or height > max_height:
        raise ValidationError(
            _("Image dimensions must not exceed %(max_width)s x %(max_height)s pixels."),
            params={"max_width": max_width, "max_height": max_height},
            code="image_too_large",
        )


def validate_rating(value):
    """
    Validate that a rating is between 1 and 5.
    """
    if value < 1 or value > 5:
        raise ValidationError(
            _("Rating must be between 1 and 5."), code="invalid_rating"
        )