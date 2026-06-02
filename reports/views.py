from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import date, timedelta
from collections import defaultdict
import json


@login_required
def reports_home(request):
    user  = request.user
    today = timezone.localdate()

    # ── Date range selector ───────────────────────────────────────────────
    range_str = request.GET.get('range', '30')
    try:
        days = int(range_str)
    except ValueError:
        days = 30
    if days not in [7, 30, 90]:
        days = 30

    start_date = today - timedelta(days=days - 1)

    # ── Tasks points (DailyLog) ───────────────────────────────────────────
    from tasks.models import DailyLog, Task, PRIORITY_POINTS, SKIP_DEDUCTION

    daily_logs = DailyLog.objects.filter(
        user=user, date__gte=start_date, date__lte=today
    ).order_by('date')

    # ── Willpower points ──────────────────────────────────────────────────
    wp_by_date = defaultdict(int)
    try:
        from tracker.models import WillpowerTask, WILLPOWER_POINTS, WILLPOWER_DEDUCT
        wp_tasks = WillpowerTask.objects.filter(
            user=user, due_date__gte=start_date, due_date__lte=today
        )
        for wt in wp_tasks:
            d = str(wt.due_date)
            if wt.status == 'completed':
                wp_by_date[d] += WILLPOWER_POINTS
            elif wt.status == 'skipped':
                wp_by_date[d] -= WILLPOWER_DEDUCT
    except Exception:
        pass

    # ── Diet points ───────────────────────────────────────────────────────
    diet_by_date = defaultdict(int)
    try:
        from diet.models import DietLog
        diet_logs = DietLog.objects.filter(
            user=user, date__gte=start_date, date__lte=today
        )
        for dl in diet_logs:
            diet_by_date[str(dl.date)] = dl.points_earned
    except Exception:
        pass

    # ── Build date series ─────────────────────────────────────────────────
    date_labels   = []
    task_pts      = []
    wp_pts        = []
    diet_pts      = []
    total_pts     = []
    day_statuses  = []
    streak_data   = []

    log_map = {str(l.date): l for l in daily_logs}

    for i in range(days):
        d     = start_date + timedelta(days=i)
        d_str = str(d)
        date_labels.append(d.strftime('%d %b'))

        log    = log_map.get(d_str)
        t_pts  = log.total_points if log else 0
        w_pts  = wp_by_date.get(d_str, 0)
        di_pts = diet_by_date.get(d_str, 0)

        task_pts.append(t_pts)
        wp_pts.append(w_pts)
        diet_pts.append(di_pts)
        total_pts.append(t_pts + w_pts + di_pts)
        day_statuses.append(log.day_status if log else 'none')
        streak_data.append(log.streak if log else 0)

    # ── Summary stats ─────────────────────────────────────────────────────
    total_task_pts  = sum(p for p in task_pts  if p > 0)
    total_wp_pts    = sum(p for p in wp_pts    if p > 0)
    total_diet_pts  = sum(p for p in diet_pts  if p > 0)
    grand_total     = total_task_pts + total_wp_pts + total_diet_pts

    win_days     = sum(1 for s in day_statuses if s == 'win')
    survive_days = sum(1 for s in day_statuses if s == 'survive')
    lose_days    = sum(1 for s in day_statuses if s == 'lose')
    active_days  = win_days + survive_days + lose_days

    max_streak   = max(streak_data) if streak_data else 0
    cur_streak   = streak_data[-1]  if streak_data else 0

    # Pie chart — points breakdown
    pie_data = [total_task_pts, total_wp_pts, total_diet_pts]

    # Day status donut
    donut_data = [win_days, survive_days, lose_days]

    # Best day
    if total_pts:
        best_idx  = total_pts.index(max(total_pts))
        best_day  = date_labels[best_idx]
        best_pts  = total_pts[best_idx]
    else:
        best_day, best_pts = '-', 0

    # Avg per active day
    avg_pts = round(grand_total / active_days, 1) if active_days else 0

    context = {
        'days':           days,
        'start_date':     start_date,
        'today':          today,
        # Chart data (JSON)
        'date_labels':    json.dumps(date_labels),
        'task_pts':       json.dumps(task_pts),
        'wp_pts':         json.dumps(wp_pts),
        'diet_pts':       json.dumps(diet_pts),
        'total_pts':      json.dumps(total_pts),
        'pie_data':       json.dumps(pie_data),
        'donut_data':     json.dumps(donut_data),
        'streak_data':    json.dumps(streak_data),
        # Summary
        'total_task_pts':  total_task_pts,
        'total_wp_pts':    total_wp_pts,
        'total_diet_pts':  total_diet_pts,
        'grand_total':     grand_total,
        'win_days':        win_days,
        'survive_days':    survive_days,
        'lose_days':       lose_days,
        'active_days':     active_days,
        'max_streak':      max_streak,
        'cur_streak':      cur_streak,
        'best_day':        best_day,
        'best_pts':        best_pts,
        'avg_pts':         avg_pts,
        # User
        'user_level':      user.level,
        'user_xp':         user.total_xp,
    }

    context['range_options'] = [(7, '7 Days'), (30, '30 Days'), (90, '90 Days')]
    return render(request, 'reports/home.html', context)
    