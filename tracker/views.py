from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import WillpowerTask, MealEntry, WILLPOWER_POINTS, WILLPOWER_DEDUCT
from datetime import date, timedelta


# ─── Helpers ────────────────────────────────────────────────

def sync_willpower_to_daily(user, log_date=None):
    if log_date is None:
        log_date = timezone.localdate()
    try:
        from tasks.views import recalculate_daily_points
        recalculate_daily_points(user, log_date)
    except Exception:
        pass


# ─── Willpower Views ─────────────────────────────────────────

@login_required
def willpower(request):
    today = timezone.localdate()

    # Date navigation
    date_str = request.GET.get('date') or request.POST.get('selected_date')
    try:
        selected_date = date.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    is_today  = (selected_date == today)

    if request.method == 'POST':
        action = request.POST.get('action')
        title  = request.POST.get('title', '').strip()

        if action == 'add' and title:
            WillpowerTask.objects.create(
                user     = request.user,
                title    = title,
                due_date = selected_date,
            )
            messages.success(request, f'Challenge added: "{title}"')

        return redirect(f'/tracker/willpower/?date={selected_date}')

    tasks     = WillpowerTask.objects.filter(user=request.user, due_date=selected_date)
    pending   = tasks.filter(status='pending')
    completed = tasks.filter(status='completed')
    skipped   = tasks.filter(status='skipped')

    wp_points = sum(
        WILLPOWER_POINTS if t.status == 'completed' else
        -WILLPOWER_DEDUCT if t.status == 'skipped' else 0
        for t in tasks
    )

    context = {
        'today':         today,
        'selected_date': selected_date,
        'prev_date':     prev_date,
        'next_date':     next_date,
        'is_today':      is_today,
        'pending':       pending,
        'completed':     completed,
        'skipped':       skipped,
        'tasks':         tasks,
        'wp_points':     wp_points,
    }
    return render(request, 'tracker/willpower.html', context)


@login_required
def complete_wp_task(request, task_id):
    task = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    if task.status == 'pending':
        task.status = 'completed'
        task.save()
        sync_willpower_to_daily(request.user, task.due_date)
    return redirect(f'/tracker/willpower/?date={task.due_date}')


@login_required
def skip_wp_task(request, task_id):
    task = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    if task.status == 'pending':
        task.status = 'skipped'
        task.save()
        sync_willpower_to_daily(request.user, task.due_date)
    return redirect(f'/tracker/willpower/?date={task.due_date}')


@login_required
def delete_wp_task(request, task_id):
    task     = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    due_date = task.due_date
    task.delete()
    sync_willpower_to_daily(request.user, due_date)
    messages.success(request, 'Challenge deleted.')
    return redirect(f'/tracker/willpower/?date={due_date}')


@login_required
def undo_wp_task(request, task_id):
    task = get_object_or_404(WillpowerTask, id=task_id, user=request.user)
    if task.status != 'pending':
        task.status = 'pending'
        task.save()
        sync_willpower_to_daily(request.user, task.due_date)
    return redirect(f'/tracker/willpower/?date={task.due_date}')


# ─── Diet Views ──────────────────────────────────────────────

@login_required
def diet(request):
    today = timezone.localdate()

    if request.method == 'POST':
        meal_type   = request.POST.get('meal_type')
        description = request.POST.get('description', '').strip()
        is_healthy  = request.POST.get('is_healthy') == 'on'

        if description:
            MealEntry.objects.create(
                user=request.user, date=today,
                meal_type=meal_type, description=description,
                is_healthy=is_healthy,
            )
            messages.success(request, f'{meal_type.capitalize()} logged! {"🥗 Healthy" if is_healthy else "🍔 Treat"}')
        return redirect('diet')

    today_meals   = MealEntry.objects.filter(user=request.user, date=today)
    week_ago      = today - timedelta(days=7)
    week_meals    = MealEntry.objects.filter(user=request.user, date__gte=week_ago)
    total_meals   = week_meals.count()
    healthy_meals = week_meals.filter(is_healthy=True).count()
    healthy_pct   = round(healthy_meals / total_meals * 100) if total_meals else 0

    context = {
        'today': today, 'today_meals': today_meals,
        'total_meals': total_meals, 'healthy_pct': healthy_pct,
        'healthy_meals': healthy_meals,
    }
    return render(request, 'tracker/diet.html', context)