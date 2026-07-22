from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from .models import (
    Task, DailyLog, PRIORITY_POINTS, SKIP_DEDUCTION, LOSE_PUNISHMENT,
    Boss, BossChallenge, BossChallengeProgress, BossDefeat,
    get_pending_boss, get_auto_verify_info, sync_auto_challenges,
)
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

    # Boss check: if XP threshold for next level was hit but boss isn't
    # defeated yet, boss_pending flips True (see check_level_up). Instead of
    # a hard redirect (which used to lock the user out of the dashboard
    # entirely), we just surface a banner — tasks/diet/willpower stay usable
    # while the boss fight is pending. The banner only ever appears AFTER
    # the XP requirement is met (never as an early preview).
    pending_boss = get_pending_boss(user, user.level) if user.boss_pending else None

    # One-shot "Level Complete" popup, set by defeat_boss() after a level-up.
    level_up_popup = request.session.pop('show_level_up', None)

    context = {
        'log':            log,
        'tasks':          tasks,
        'pending':        pending,
        'completed':      completed,
        'skipped':        skipped,
        'wp_tasks':       wp_tasks,
        'today':          today,
        'selected_date':  selected_date,
        'prev_date':      prev_date,
        'next_date':      next_date,
        'is_today':       is_today,
        'cur_level':      cur,
        'nxt_level':      nxt,
        'xp_pct':         user.xp_progress_pct(),
        'xp_to_next':     user.xp_to_next_level(),
        'days_left':      user.days_left(),
        'win_pts':        log.win_threshold,
        'survive_pts':    log.survive_threshold,
        'pending_boss':   pending_boss,
        'level_up_popup': level_up_popup,
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

        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if title:
            task = Task.objects.create(
                user=request.user, title=title,
                priority=priority, due_date=due_date,
            )
            log = recalculate_daily_points(request.user, due_date)
            user = request.user
            messages.success(request, f'Task "{title}" added!')

            if is_ajax:
                return JsonResponse({
                    'ok':         True,
                    'task_id':    task.id,
                    'title':      task.title,
                    'priority':   task.priority,
                    'stars':      task.stars(),
                    'points':     task.get_points(),
                    'points_total':   log.total_points,
                    'day_status':     log.day_status,
                    'streak':         log.streak,
                    'total_xp':       user.total_xp,
                    'level':          user.level,
                    'xp_pct':         user.xp_progress_pct(),
                    'win_pts':        log.win_threshold,
                })
        elif is_ajax:
            return JsonResponse({'ok': False, 'error': 'Title required.'}, status=400)

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


# ─── Boss Battle Views ────────────────────────────────────────────────────

@login_required
def boss_battle(request):
    user = request.user
    boss = get_pending_boss(user, user.level)

    if boss is None:
        # Nothing left to fight — clear the flag and let the next dashboard
        # visit trigger the actual level up via check_level_up().
        if user.boss_pending:
            user.boss_pending = False
            user.save()
        messages.success(request, 'Boss already defeated! Leveling up...')
        user.check_level_up()
        return redirect('dashboard')

    challenges = boss.challenges.all()

    # Sync any auto-verifiable (e.g. "Reach N total XP") challenges against
    # real stats before building the display list, so it's never stale.
    sync_auto_challenges(boss, user)

    progress_map = {
        p.challenge_id: p.completed
        for p in BossChallengeProgress.objects.filter(user=user, challenge__boss=boss)
    }

    def classify_icon(desc):
        d = desc.lower()
        if 'xp' in d:
            return '⭐'
        if 'streak' in d or 'row' in d or 'straight' in d:
            return '🔥'
        if 'pts' in d or 'win' in d or 'score' in d:
            return '🎯'
        if 'diet' in d or 'meal' in d:
            return '🥗'
        return '⚔️'

    challenge_data = []
    for i, c in enumerate(challenges):
        is_auto, is_met, auto_label = get_auto_verify_info(c.description, user)
        completed = is_met if is_auto else progress_map.get(c.id, False)
        challenge_data.append({
            'challenge':   c,
            'completed':   completed,
            'icon':        classify_icon(c.description),
            'index':       i + 1,
            'is_auto':     is_auto,
            'auto_label':  auto_label,
        })
    all_done = challenges.exists() and all(cd['completed'] for cd in challenge_data)

    total_count     = challenges.count()
    completed_count = sum(1 for cd in challenge_data if cd['completed'])
    hp_pct = 100 if total_count == 0 else round(
        max(0, (total_count - completed_count) / total_count * 100)
    )

    # Level 10 (LUST) gets a special "fusion" intro — small glowing orbs for
    # each of the previous 9 bosses converge into the final form.
    fusion_names = []
    if boss.level_number == 10:
        fusion_names = list(
            Boss.objects.filter(level_number__lt=10, boss_type='final')
            .order_by('level_number').values_list('name', flat=True)
        )

    context = {
        'boss':           boss,
        'challenge_data': challenge_data,
        'all_done':       all_done,
        'user_level':     user.level,
        'hp_pct':         hp_pct,
        'fusion_names':   fusion_names,
    }
    return render(request, 'tasks/boss_battle.html', context)


@login_required
def complete_challenge(request, challenge_id):
    challenge = get_object_or_404(BossChallenge, id=challenge_id)
    progress, _ = BossChallengeProgress.objects.get_or_create(
        user=request.user, challenge=challenge
    )
    if not progress.completed:
        progress.mark_complete()
        messages.success(request, f'✅ Challenge cleared: {challenge.description}')
    return redirect('boss_battle')


@login_required
def defeat_boss(request, boss_id):
    """Called once all of a boss's challenges are marked complete."""
    boss = get_object_or_404(Boss, id=boss_id)
    user = request.user
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not boss.challenges_completed_by(user):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Complete all challenges first.'}, status=400)
        messages.error(request, 'Complete all challenges before facing the boss!')
        return redirect('boss_battle')

    BossDefeat.objects.get_or_create(user=user, boss=boss)
    messages.success(request, f'🏆 {boss.name} defeated!')

    # Re-run the gate: if this was the last boss for the level, this will
    # actually perform the level up now.
    leveled_up = user.check_level_up()
    if leveled_up:
        messages.success(request, f'🎉 Level Up! Welcome to Level {user.level}!')
        # Dashboard reads and clears this to show the "Level Complete" popup.
        request.session['show_level_up'] = {
            'level': user.level,
            'title': user.title,
        }
        redirect_url = '/dashboard/'
    else:
        redirect_url = '/dashboard/boss/'

    if is_ajax:
        return JsonResponse({'ok': True, 'leveled_up': leveled_up, 'redirect': redirect_url})

    return redirect('dashboard') if leveled_up else redirect('boss_battle')