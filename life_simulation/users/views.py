from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .forms import RegisterForm, LoginForm, ProfileForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome, {user.get_display_name()}! Your journey begins now. 🎮')
        return redirect('dashboard')

    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f'Welcome back, {user.get_display_name()}! 🔥')
        return redirect(request.GET.get('next', 'dashboard'))

    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have logged out. See you tomorrow, protagonist.')
    return redirect('login')


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_badges(user, win_days, tasks_completed, max_streak):
    """Return list of badge dicts with unlocked status."""
    badges = [
        {
            'emoji': '⚔️',
            'name':  'First Blood',
            'desc':  'Complete your first task',
            'unlocked': tasks_completed >= 1,
        },
        {
            'emoji': '🏆',
            'name':  'Win Streak',
            'desc':  '3 Win days in a row',
            'unlocked': max_streak >= 3,
        },
        {
            'emoji': '🔥',
            'name':  'On Fire',
            'desc':  '7 day streak',
            'unlocked': max_streak >= 7,
        },
        {
            'emoji': '💪',
            'name':  'Warrior',
            'desc':  '10 Win days total',
            'unlocked': win_days >= 10,
        },
        {
            'emoji': '⚡',
            'name':  'Grinder',
            'desc':  'Complete 50 tasks',
            'unlocked': tasks_completed >= 50,
        },
        {
            'emoji': '👑',
            'name':  'Legend',
            'desc':  'Reach Level 5',
            'unlocked': user.level >= 5,
        },
        {
            'emoji': '🌙',
            'name':  'Night Owl',
            'desc':  '30 days active',
            'unlocked': (win_days + getattr(user, '_survive_days', 0)) >= 30,
        },
        {
            'emoji': '🥗',
            'name':  'Diet Master',
            'desc':  'Setup diet profile',
            'unlocked': hasattr(user, 'diet_profile'),
        },
    ]
    return badges


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
def profile_view(request):
    user  = request.user
    today = timezone.localdate()

    # ── Handle POST actions ───────────────────────────────────────────────
    if request.method == 'POST':
        action = request.POST.get('action', 'update_info')

        if action == 'update_info':
            form = ProfileForm(request.POST, request.FILES, instance=user)
            if form.is_valid():
                form.save()
                messages.success(request, '✅ Profile updated!')
            else:
                messages.error(request, '⚠️ Please fix the errors below.')
            return redirect('profile')

        elif action == 'change_password':
            old_pw  = request.POST.get('old_password', '')
            new_pw1 = request.POST.get('new_password1', '')
            new_pw2 = request.POST.get('new_password2', '')

            if not user.check_password(old_pw):
                messages.error(request, '❌ Current password is incorrect.')
            elif new_pw1 != new_pw2:
                messages.error(request, '❌ New passwords do not match.')
            elif len(new_pw1) < 6:
                messages.error(request, '❌ Password must be at least 6 characters.')
            else:
                user.set_password(new_pw1)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, '🔑 Password changed successfully!')
            return redirect('profile')

    # ── Stats ─────────────────────────────────────────────────────────────
    from tasks.models import DailyLog, Task

    all_logs = DailyLog.objects.filter(user=user)
    win_days     = all_logs.filter(day_status='win').count()
    survive_days = all_logs.filter(day_status='survive').count()
    lose_days    = all_logs.filter(day_status='lose').count()

    tasks_completed = Task.objects.filter(user=user, status='completed').count()

    streak_list = list(all_logs.order_by('date').values_list('streak', flat=True))
    max_streak  = max(streak_list) if streak_list else 0
    cur_streak  = streak_list[-1]  if streak_list else 0

    # Store survive days for badge helper
    user._survive_days = survive_days

    # ── Badges ────────────────────────────────────────────────────────────
    badges          = get_badges(user, win_days, tasks_completed, max_streak)
    badges_unlocked = sum(1 for b in badges if b['unlocked'])

    # ── Level data ────────────────────────────────────────────────────────
    cur_level = user.current_level_data()
    nxt_level = user.next_level_data()
    xp_pct    = user.xp_progress_pct()
    xp_to_next = user.xp_to_next_level()

    # ── Character title based on level ────────────────────────────────────
    titles = {
        1: 'Novice Warrior',
        2: 'Iron Warrior',
        3: 'Steel Warrior',
        4: 'Elite Warrior',
        5: 'Legendary Warrior',
    }
    character_title = titles.get(user.level, f'Level {user.level} Warrior')

    context = {
        'form':             ProfileForm(instance=user),
        'cur_level':        cur_level,
        'nxt_level':        nxt_level,
        'xp_pct':           xp_pct,
        'xp_to_next':       xp_to_next,
        'win_days':         win_days,
        'survive_days':     survive_days,
        'lose_days':        lose_days,
        'tasks_completed':  tasks_completed,
        'cur_streak':       cur_streak,
        'max_streak':       max_streak,
        'badges':           badges,
        'badges_unlocked':  badges_unlocked,
        'badges_total':     len(badges),
        'character_title':  character_title,
    }
    return render(request, 'users/profile.html', context)


@login_required
def edit_profile(request):
    """Redirect to profile — editing is handled there."""
    return redirect('profile')


@login_required
def delete_account(request):
    if request.method == 'POST':
        password = request.POST.get('confirm_password', '')
        user     = request.user

        if user.check_password(password):
            logout(request)
            user.delete()
            messages.success(request, 'Account deleted. Goodbye, Warrior. 💀')
            return redirect('login')
        else:
            messages.error(request, '❌ Incorrect password. Account not deleted.')
            return redirect('profile')

    return redirect('profile')