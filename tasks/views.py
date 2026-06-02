from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from .models import Task, DailyLog, PRIORITY_POINTS, SKIP_DEDUCTION, LOSE_PUNISHMENT
from datetime import date, timedelta


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_or_create_daily_log(user, log_date=None):
    if log_date is None:
        log_date = timezone.localdate()

    log, created = DailyLog.objects.get_or_create(user=user, date=log_date)

    if created:
        log.win_threshold     = user.get_win_pts()
        log.survive_threshold = user.get_survive_min()

        yesterday = log_date - timedelta(days=1)
        try:
            y_log = DailyLog.objects.get(user=user, date=yesterday)
            if y_log.day_status == 'lose':
                log.total_points = -LOSE_PUNISHMENT
                log.punishment   = True
        except DailyLog.DoesNotExist:
            pass
        log.save()

    return log


def recalculate_daily_points(user, log_date=None):
    if log_date is None:
        log_date = timezone.localdate()

    log    = get_or_create_daily_log(user, log_date)
    points = -LOSE_PUNISHMENT if log.punishment else 0

    for task in Task.objects.filter(user=user, due_date=log_date):
        if task.status == 'completed':
            points += task.get_points()
        elif task.status == 'skipped':
            points -= SKIP_DEDUCTION

    try:
        from tracker.models import WillpowerTask, WILLPOWER_POINTS, WILLPOWER_DEDUCT
        for wt in WillpowerTask.objects.filter(user=user, due_date=log_date):
            if wt.status == 'completed':
                points += WILLPOWER_POINTS
            elif wt.status == 'skipped':
                points -= WILLPOWER_DEDUCT
    except Exception:
        pass

    log.total_points      = points
    log.win_threshold     = user.get_win_pts()
    log.survive_threshold = user.get_survive_min()
    log.save()

    update_streak(user, log)
    update_user_xp(user)
    return log


def update_user_xp(user):
    from django.db.models import Sum
    total = DailyLog.objects.filter(
        user=user, total_points__gt=0
    ).aggregate(Sum('total_points'))['total_points__sum'] or 0

    user.total_xp  = total
    penalized      = user.check_deadline_penalty()
    leveled_up     = user.check_level_up()

    if not leveled_up and not penalized:
        user.save()

    return leveled_up, penalized


def update_streak(user, today_log):
    yesterday = today_log.date - timedelta(days=1)
    try:
        y_log = DailyLog.objects.get(user=user, date=yesterday)
        if today_log.day_status == 'win':
            today_log.streak = y_log.streak + 1
        elif today_log.day_status == 'lose':
            today_log.streak = 0
        else:
            today_log.streak = y_log.streak
    except DailyLog.DoesNotExist:
        today_log.streak = 1 if today_log.day_status == 'win' else 0
    DailyLog.objects.filter(pk=today_log.pk).update(streak=today_log.streak)


# ─── Views ───────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    today = timezone.localdate()

    date_str = request.GET.get('date')
    try:
        selected_date = date.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

    prev_date = (selected_date - timedelta(days=1)).isoformat()
    next_date = (selected_date + timedelta(days=1)).isoformat()
    is_today  = (selected_date == today)

    penalized = request.user.check_deadline_penalty()
    if penalized:
        messages.warning(request, f'⏰ Level deadline missed! Extra time given!')

    log   = get_or_create_daily_log(request.user, selected_date)
    tasks = Task.objects.filter(user=request.user, due_date=selected_date)

    pending   = tasks.filter(status='pending')
    completed = tasks.filter(status='completed')
    skipped   = tasks.filter(status='skipped')

    try:
        from tracker.models import WillpowerTask
        wp_tasks = WillpowerTask.objects.filter(user=request.user, due_date=selected_date)
    except Exception:
        wp_tasks = []

    user = request.user
    cur  = user.current_level_data()
    nxt  = user.next_level_data()

    context = {
        'log':           log,
        'tasks':         tasks,
        'pending':       pending,
        'completed':     completed,
        'skipped':       skipped,
        'wp_tasks':      wp_tasks,
        'today':         today,
        'selected_date': selected_date,
        'prev_date':     prev_date,
        'next_date':     next_date,
        'is_today':      is_today,
        'cur_level':     cur,
        'nxt_level':     nxt,
        'xp_pct':        user.xp_progress_pct(),
        'xp_to_next':    user.xp_to_next_level(),
        'days_left':     user.days_left(),
        'win_pts':       log.win_threshold,
        'survive_pts':   log.survive_threshold,
    }
    return render(request, 'tasks/dashboard.html', context)


@login_required
def add_task(request):
    if request.method == 'POST':
        title    = request.POST.get('title', '').strip()
        priority = int(request.POST.get('priority', 3))
        date_str = request.POST.get('selected_date')
        try:
            due_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
        except ValueError:
            due_date = timezone.localdate()

        if title:
            Task.objects.create(
                user=request.user, title=title,
                priority=priority, due_date=due_date,
            )
            recalculate_daily_points(request.user, due_date)
            messages.success(request, f'Task "{title}" added!')

    return redirect(f'/dashboard/?date={due_date.isoformat()}')


@login_required
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    if task.status == 'pending':
        task.status = 'completed'
        task.save()
        log  = recalculate_daily_points(request.user, task.due_date)
        user = request.user
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status':     'completed',
                'points':     log.total_points,
                'day_status': log.day_status,
                'streak':     log.streak,
                'earned':     task.get_points(),
                'total_xp':   user.total_xp,
                'level':      user.level,
                'xp_pct':     user.xp_progress_pct(),
                'xp_to_next': user.xp_to_next_level(),
                'win_pts':    log.win_threshold,
            })
    return redirect(f'/dashboard/?date={task.due_date.isoformat()}')


@login_required
def skip_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    if task.status == 'pending':
        task.status = 'skipped'
        task.save()
        log  = recalculate_daily_points(request.user, task.due_date)
        user = request.user
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status':     'skipped',
                'points':     log.total_points,
                'day_status': log.day_status,
                'streak':     log.streak,
                'deducted':   SKIP_DEDUCTION,
                'total_xp':   user.total_xp,
                'level':      user.level,
                'xp_pct':     user.xp_progress_pct(),
                'win_pts':    log.win_threshold,
            })
    return redirect(f'/dashboard/?date={task.due_date.isoformat()}')


@login_required
def delete_task(request, task_id):
    task     = get_object_or_404(Task, id=task_id, user=request.user)
    due_date = task.due_date
    task.delete()
    recalculate_daily_points(request.user, due_date)
    messages.success(request, 'Task deleted.')
    return redirect(f'/dashboard/?date={due_date.isoformat()}')


@login_required
def undo_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    if task.status != 'pending':
        task.status = 'pending'
        task.save()
        recalculate_daily_points(request.user, task.due_date)
    return redirect(f'/dashboard/?date={task.due_date.isoformat()}')