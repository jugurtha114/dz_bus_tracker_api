"""
Admin analytics endpoints (R22).

All endpoints require IsAdmin permission.

Endpoints:
  GET /api/v1/admin/stats/ridership/    ?line=&date_from=&date_to=
  GET /api/v1/admin/stats/lines/        summary stats per line
  GET /api/v1/admin/stats/stops/busiest/  top-N busiest stops
"""
from datetime import date, timedelta

from django.db.models import Avg, Count, F, Sum, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdmin
from apps.tracking.models import Trip, LocationUpdate, WaitingCountReport
from apps.lines.models import Line, Stop


class RidershipStatsView(APIView):
    """
    GET /api/v1/admin/stats/ridership/

    Query parameters:
      line       (UUID, optional) – filter to a single line
      date_from  (YYYY-MM-DD, optional) – default: 30 days ago
      date_to    (YYYY-MM-DD, optional) – default: today
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        # --- Parse date range ---
        today = timezone.now().date()
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')

        try:
            date_from = date.fromisoformat(date_from_str) if date_from_str else today - timedelta(days=30)
            date_to = date.fromisoformat(date_to_str) if date_to_str else today
        except ValueError:
            return Response(
                {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_from > date_to:
            return Response(
                {'detail': 'date_from must be before or equal to date_to.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        trips_qs = Trip.objects.filter(
            start_time__date__gte=date_from,
            start_time__date__lte=date_to,
        )

        line_id = request.query_params.get('line')
        if line_id:
            trips_qs = trips_qs.filter(line_id=line_id)

        # Daily ridership: proxy is max_passengers per trip, summed per day
        daily = (
            trips_qs
            .annotate(trip_date=TruncDate('start_time'))
            .values('trip_date')
            .annotate(
                total_trips=Count('id'),
                total_passengers=Sum('max_passengers'),
                avg_occupancy=Avg(
                    F('max_passengers') * 1.0
                ),
            )
            .order_by('trip_date')
        )

        return Response({
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'line': line_id,
            'daily': list(daily),
        })


class LineStatsView(APIView):
    """
    GET /api/v1/admin/stats/lines/

    Returns per-line summary: trip count, average occupancy, average trip
    duration (minutes), total passengers.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        today = timezone.now().date()

        try:
            date_from = date.fromisoformat(date_from_str) if date_from_str else today - timedelta(days=30)
            date_to = date.fromisoformat(date_to_str) if date_to_str else today
        except ValueError:
            return Response(
                {'detail': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        trips_qs = Trip.objects.filter(
            start_time__date__gte=date_from,
            start_time__date__lte=date_to,
            is_completed=True,
        ).select_related('line')

        stats = (
            trips_qs
            .values('line__id', 'line__name', 'line__code')
            .annotate(
                total_trips=Count('id'),
                total_passengers=Sum('max_passengers'),
                avg_passengers=Avg('max_passengers'),
                avg_speed_kmh=Avg('average_speed'),
                total_distance_km=Sum('distance'),
            )
            .order_by('-total_trips')
        )

        return Response({
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'lines': list(stats),
        })


class BusiestStopsView(APIView):
    """
    GET /api/v1/admin/stats/stops/busiest/

    Query parameters:
      top_n  (int, default 20) – number of stops to return
      date_from / date_to – same as ridership

    Ranking by waiting-count reports submitted at each stop in the period.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        today = timezone.now().date()
        date_from_str = request.query_params.get('date_from')
        date_to_str = request.query_params.get('date_to')
        top_n_str = request.query_params.get('top_n', '20')

        try:
            date_from = date.fromisoformat(date_from_str) if date_from_str else today - timedelta(days=30)
            date_to = date.fromisoformat(date_to_str) if date_to_str else today
            top_n = min(int(top_n_str), 100)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Invalid parameters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reports_qs = WaitingCountReport.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
            stop__isnull=False,
        )

        top_stops = (
            reports_qs
            .values('stop__id', 'stop__name', 'stop__latitude', 'stop__longitude')
            .annotate(
                report_count=Count('id'),
                avg_waiting=Avg('reported_count'),
                total_waiting=Sum('reported_count'),
            )
            .order_by('-report_count')[:top_n]
        )

        return Response({
            'date_from': date_from.isoformat(),
            'date_to': date_to.isoformat(),
            'top_n': top_n,
            'stops': list(top_stops),
        })
