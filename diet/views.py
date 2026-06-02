import json
from groq import Groq
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.db.models import Q
from datetime import date, timedelta
from .models import (
    DietProfile, FoodItem, MealLog, DietLog,
    DIET_WIN_POINTS, DIET_CHEAT_PENALTY, PHYSIQUE_CARDS
)

client = Groq(api_key="GROQ_API_KEY")  # <-- apni Groq key yahan daal

MEAL_EMOJIS = {
    'breakfast': '🌅',
    'lunch':     '☀️',
    'dinner':    '🌙',
    'snack':     '🍎',
}

# ── Local food database (seed data) ──────────────────────────────────────────
SEED_FOODS = [
    # name, cal/100, protein, carbs, fat, unit
    ('Rice (cooked)',         130,  2.7, 28.2,  0.3, 'g'),
    ('Chapati / Roti',        297,  8.0, 52.0,  7.0, 'g'),
    ('Dal (cooked)',          116,  7.5, 20.0,  0.4, 'g'),
    ('Paneer',                265, 18.3,  1.2, 20.8, 'g'),
    ('Chicken Breast',        165, 31.0,  0.0,  3.6, 'g'),
    ('Egg (whole)',           155, 13.0,  1.1, 11.0, 'g'),
    ('Egg White',              52, 11.0,  0.7,  0.2, 'g'),
    ('Milk (full fat)',        61,  3.2,  4.8,  3.3, 'ml'),
    ('Banana',                 89,  1.1, 22.8,  0.3, 'g'),
    ('Apple',                  52,  0.3, 13.8,  0.2, 'g'),
    ('Oats',                  389, 16.9, 66.3,  6.9, 'g'),
    ('Whey Protein (scoop)',  120, 24.0,  3.0,  2.0, 'g'),
    ('Peanut Butter',         588, 25.0, 20.0, 50.0, 'g'),
    ('White Bread',           265,  9.0, 49.0,  3.2, 'g'),
    ('Sweet Potato',           86,  1.6, 20.1,  0.1, 'g'),
    ('Broccoli',               34,  2.8,  6.6,  0.4, 'g'),
    ('Almonds',               579, 21.2, 21.7, 49.9, 'g'),
    ('Curd / Yogurt',          98,  3.5, 11.4,  4.3, 'g'),
    ('Samosa (1 piece)',       262,  3.5, 24.0, 17.0, 'pcs'),
    ('Pizza (1 slice)',        266, 11.0, 33.0, 10.0, 'pcs'),
    ('Burger (regular)',       295, 17.0, 24.0, 14.0, 'pcs'),
    ('Cold Drink / Soda',      42,  0.0, 10.6,  0.0, 'ml'),
    ('Olive Oil',              884,  0.0,  0.0,100.0, 'g'),
    ('Idli (1 piece)',          39,  2.0,  8.0,  0.1, 'pcs'),
    ('Dosa',                   168,  3.9, 26.4,  5.6, 'g'),
]


def ensure_seed_foods():
    """Seed global food DB if empty."""
    if FoodItem.objects.filter(user__isnull=True).count() == 0:
        foods = [
            FoodItem(
                name=name, calories_per_100=cal,
                protein_per_100=pro, carbs_per_100=carb,
                fat_per_100=fat, base_unit=unit, user=None
            )
            for name, cal, pro, carb, fat, unit in SEED_FOODS
        ]
        FoodItem.objects.bulk_create(foods)


# ── AI helpers ────────────────────────────────────────────────────────────────

def ai_estimate_food(food_name, quantity, unit):
    """Ask Groq for calorie/macro estimate."""
    prompt = f"""You are a nutrition database. For "{food_name}" at {quantity} {unit}, return ONLY a JSON object with no extra text, no markdown:
{{
  "calories": <number>,
  "protein_g": <number>,
  "carbs_g": <number>,
  "fat_g": <number>,
  "calories_per_100": <number>,
  "protein_per_100": <number>,
  "carbs_per_100": <number>,
  "fat_per_100": <number>,
  "base_unit": "<g or ml or pcs>"
}}
All values must be numbers (floats)."""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return None


def ai_generate_diet_plan(profile_data):
    """Generate personalized diet plan using Groq."""
    prompt = f"""You are an expert nutritionist. Create a personalized diet plan for:
- Gender: {profile_data['gender']}
- Age: {profile_data['age']} years
- Weight: {profile_data['weight_kg']} kg
- Height: {profile_data['height_cm']} cm
- Activity Level: {profile_data['activity_level']}
- Goal: {profile_data['physique_goal']}

Return ONLY a JSON object with no extra text, no markdown:
{{
  "daily_calories": <int>,
  "protein_g": <int>,
  "carbs_g": <int>,
  "fat_g": <int>,
  "plan_summary": "<2-3 sentence summary>",
  "meal_tips": ["<tip1>", "<tip2>", "<tip3>"],
  "foods_to_eat": ["<food1>", "<food2>", "<food3>", "<food4>", "<food5>"],
  "foods_to_avoid": ["<food1>", "<food2>", "<food3>"]
}}"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception:
        return None


# ── Daily log helpers ─────────────────────────────────────────────────────────

def recalculate_diet_log(user, log_date):
    meals      = MealLog.objects.filter(user=user, date=log_date)
    total_cal  = sum(m.calories  for m in meals)
    total_pro  = sum(m.protein_g for m in meals)
    total_carb = sum(m.carbs_g   for m in meals)
    total_fat  = sum(m.fat_g     for m in meals)
    has_cheat  = meals.filter(is_cheat=True).exists()

    diet_log, _ = DietLog.objects.get_or_create(user=user, date=log_date)
    diet_log.total_calories = total_cal
    diet_log.total_protein  = total_pro
    diet_log.total_carbs    = total_carb
    diet_log.total_fat      = total_fat
    diet_log.has_cheat_meal = has_cheat

    try:
        profile       = user.diet_profile
        lower         = profile.calorie_lower()
        upper         = profile.calorie_upper()
        survive_lower = int(lower * 0.85)

        if lower <= total_cal <= upper:
            diet_log.day_status = 'win'
            pts = DIET_WIN_POINTS
        elif survive_lower <= total_cal < lower or upper < total_cal <= int(upper * 1.1):
            diet_log.day_status = 'survive'
            pts = 5
        else:
            diet_log.day_status = 'lose'
            pts = 0

        if has_cheat:
            pts -= DIET_CHEAT_PENALTY

        diet_log.points_earned = pts
    except DietProfile.DoesNotExist:
        diet_log.day_status    = 'ongoing'
        diet_log.points_earned = 0

    diet_log.save()
    return diet_log


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
def onboarding(request):
    if hasattr(request.user, 'diet_profile'):
        return redirect('diet')
    return render(request, 'diet/onboarding.html', {
        'physique_cards': PHYSIQUE_CARDS,
    })


@login_required
def onboarding_details(request):
    if hasattr(request.user, 'diet_profile'):
        return redirect('diet')

    goal = request.GET.get('goal') or request.POST.get('goal', 'maintain')
    if goal not in PHYSIQUE_CARDS:
        goal = 'maintain'

    if request.method == 'POST':
        gender    = request.POST.get('gender', 'male')
        age       = int(request.POST.get('age', 25))
        weight_kg = float(request.POST.get('weight_kg', 70))
        height_cm = float(request.POST.get('height_cm', 170))
        activity  = request.POST.get('activity_level', 'moderate')

        if goal == 'custom':
            DietProfile.objects.create(
                user=request.user, gender=gender, age=age,
                weight_kg=weight_kg, height_cm=height_cm,
                activity_level=activity, physique_goal=goal,
                daily_calories=int(request.POST.get('daily_calories', 2000)),
                protein_g=int(request.POST.get('protein_g', 150)),
                carbs_g=int(request.POST.get('carbs_g', 250)),
                fat_g=int(request.POST.get('fat_g', 65)),
                ai_plan="Custom plan set by user.",
            )
            messages.success(request, '✅ Custom diet plan saved!')
            return redirect('diet')

        plan_data = ai_generate_diet_plan({
            'gender':         gender,
            'age':            age,
            'weight_kg':      weight_kg,
            'height_cm':      height_cm,
            'activity_level': activity,
            'physique_goal':  goal,
        })

        if plan_data:
            ai_text = json.dumps({
                'summary': plan_data.get('plan_summary', ''),
                'tips':    plan_data.get('meal_tips', []),
                'eat':     plan_data.get('foods_to_eat', []),
                'avoid':   plan_data.get('foods_to_avoid', []),
            })
            DietProfile.objects.create(
                user=request.user, gender=gender, age=age,
                weight_kg=weight_kg, height_cm=height_cm,
                activity_level=activity, physique_goal=goal,
                daily_calories=plan_data['daily_calories'],
                protein_g=plan_data['protein_g'],
                carbs_g=plan_data['carbs_g'],
                fat_g=plan_data['fat_g'],
                ai_plan=ai_text,
            )
            messages.success(request, '🤖 AI diet plan generated!')
            return redirect('diet_plan_result')
        else:
            messages.error(request, '⚠️ AI error. Please try again.')

    return render(request, 'diet/onboarding_details.html', {
        'goal': goal,
        'card': PHYSIQUE_CARDS[goal],
        'activity_choices': [
            ('sedentary',   'Sedentary (No exercise)'),
            ('light',       'Light (1-2x/week)'),
            ('moderate',    'Moderate (3-4x/week)'),
            ('active',      'Active (5-6x/week)'),
            ('very_active', 'Very Active (2x/day)'),
        ],
    })


@login_required
def diet_plan_result(request):
    try:
        profile   = request.user.diet_profile
        plan_data = json.loads(profile.ai_plan) if profile.ai_plan else {}
    except Exception:
        return redirect('diet')

    macro_items = [
        ('Calories', profile.daily_calories, '#7c6fff'),
        ('Protein',  f"{profile.protein_g}g", '#4cff91'),
        ('Carbs',    f"{profile.carbs_g}g",   '#f5c842'),
        ('Fat',      f"{profile.fat_g}g",     '#ff4c6b'),
    ]
    return render(request, 'diet/plan_result.html', {
        'profile':     profile,
        'plan_data':   plan_data,
        'macro_items': macro_items,
    })


@login_required
def diet_home(request):
    ensure_seed_foods()

    if not hasattr(request.user, 'diet_profile'):
        return redirect('diet_onboarding')

    profile = request.user.diet_profile
    today   = timezone.localdate()

    date_str = request.GET.get('date')
    try:
        selected_date = date.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

    prev_date = selected_date - timedelta(days=1)
    next_date = selected_date + timedelta(days=1)
    is_today  = (selected_date == today)

    meals    = MealLog.objects.filter(user=request.user, date=selected_date)
    diet_log = recalculate_diet_log(request.user, selected_date)

    grouped = {}
    for mtype, mlabel in MealLog.MEAL_CHOICES:
        group_meals = meals.filter(meal_type=mtype)
        grouped[mtype] = {
            'label':      mlabel,
            'emoji':      MEAL_EMOJIS[mtype],
            'items':      group_meals,
            'total_kcal': sum(m.calories for m in group_meals),
        }

    def pct(val, target):
        return min(int(val / target * 100), 100) if target else 0

    return render(request, 'diet/home.html', {
        'profile':            profile,
        'diet_log':           diet_log,
        'grouped':            grouped,
        'selected_date':      selected_date,
        'prev_date':          prev_date,
        'next_date':          next_date,
        'is_today':           is_today,
        'today':              today,
        'calorie_pct':        pct(diet_log.total_calories, profile.daily_calories),
        'protein_pct':        pct(diet_log.total_protein,  profile.protein_g),
        'carbs_pct':          pct(diet_log.total_carbs,    profile.carbs_g),
        'fat_pct':            pct(diet_log.total_fat,      profile.fat_g),
        'meal_types':         MealLog.MEAL_CHOICES,
        'meal_emojis':        MEAL_EMOJIS,
        'diet_cheat_penalty': DIET_CHEAT_PENALTY,
    })


@login_required
def search_food(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'results': []})

    qs = FoodItem.objects.filter(
        Q(name__icontains=query),
        Q(user__isnull=True) | Q(user=request.user)
    )[:10]

    results = [{
        'id':   f.id,
        'name': f.name,
        'cal':  f.calories_per_100,
        'pro':  f.protein_per_100,
        'carb': f.carbs_per_100,
        'fat':  f.fat_per_100,
        'unit': f.base_unit,
    } for f in qs]

    return JsonResponse({'results': results})


@login_required
def ai_lookup_food(request):
    food_name = request.GET.get('name', '').strip()
    quantity  = float(request.GET.get('qty', 100))
    unit      = request.GET.get('unit', 'g')

    if not food_name:
        return JsonResponse({'error': 'No food name'}, status=400)

    data = ai_estimate_food(food_name, quantity, unit)
    if data:
        return JsonResponse({'success': True, 'data': data})
    return JsonResponse({'success': False, 'error': 'AI estimation failed'}, status=500)


@login_required
def add_meal(request):
    if request.method != 'POST':
        return redirect('diet')

    date_str  = request.POST.get('date')
    meal_type = request.POST.get('meal_type', 'lunch')
    food_id   = request.POST.get('food_id', '')
    food_name = request.POST.get('food_name', '').strip()
    quantity  = float(request.POST.get('quantity', 100))
    unit      = request.POST.get('unit', 'g')
    is_cheat  = request.POST.get('is_cheat') == 'on'
    notes     = request.POST.get('notes', '')

    cal  = float(request.POST.get('calories', 0))
    pro  = float(request.POST.get('protein_g', 0))
    carb = float(request.POST.get('carbs_g', 0))
    fat  = float(request.POST.get('fat_g', 0))

    try:
        log_date = date.fromisoformat(date_str) if date_str else timezone.localdate()
    except ValueError:
        log_date = timezone.localdate()

    food_item = None
    if food_id:
        try:
            food_item = FoodItem.objects.get(
                Q(id=int(food_id)),
                Q(user__isnull=True) | Q(user=request.user)
            )
            macros    = food_item.get_macros(quantity)
            cal, pro, carb, fat = macros['calories'], macros['protein'], macros['carbs'], macros['fat']
            food_name = food_item.name
        except FoodItem.DoesNotExist:
            pass

    # Save AI-estimated food to DB for future use
    if not food_item and food_name:
        cal_per_100  = float(request.POST.get('cal_per_100', 0))
        pro_per_100  = float(request.POST.get('pro_per_100', 0))
        carb_per_100 = float(request.POST.get('carb_per_100', 0))
        fat_per_100  = float(request.POST.get('fat_per_100', 0))

        if cal_per_100 > 0:
            food_item = FoodItem.objects.create(
                name=food_name,
                calories_per_100=cal_per_100,
                protein_per_100=pro_per_100,
                carbs_per_100=carb_per_100,
                fat_per_100=fat_per_100,
                base_unit=unit,
                user=request.user,
                ai_estimated=True,
            )
            macros = food_item.get_macros(quantity)
            cal, pro, carb, fat = macros['calories'], macros['protein'], macros['carbs'], macros['fat']

    MealLog.objects.create(
        user=request.user, date=log_date,
        meal_type=meal_type,
        food_item=food_item,
        food_name=food_name,
        quantity=quantity, unit=unit,
        calories=cal, protein_g=pro, carbs_g=carb, fat_g=fat,
        is_cheat=is_cheat, notes=notes,
    )

    recalculate_diet_log(request.user, log_date)
    messages.success(request, f'🍽️ {food_name} logged!')
    return redirect(f'/diet/?date={log_date}')


@login_required
def delete_meal(request, meal_id):
    meal     = get_object_or_404(MealLog, id=meal_id, user=request.user)
    log_date = meal.date
    meal.delete()
    recalculate_diet_log(request.user, log_date)
    messages.success(request, 'Meal removed.')
    return redirect(f'/diet/?date={log_date}')


@login_required
def toggle_cheat(request, meal_id):
    meal          = get_object_or_404(MealLog, id=meal_id, user=request.user)
    meal.is_cheat = not meal.is_cheat
    meal.save()
    recalculate_diet_log(request.user, meal.date)
    return redirect(f'/diet/?date={meal.date}')


@login_required
def edit_profile(request):
    if not hasattr(request.user, 'diet_profile'):
        return redirect('diet_onboarding')

    profile = request.user.diet_profile

    if request.method == 'POST':
        profile.weight_kg      = float(request.POST.get('weight_kg', profile.weight_kg))
        profile.height_cm      = float(request.POST.get('height_cm', profile.height_cm))
        profile.activity_level = request.POST.get('activity_level', profile.activity_level)
        profile.daily_calories = int(request.POST.get('daily_calories', profile.daily_calories))
        profile.protein_g      = int(request.POST.get('protein_g', profile.protein_g))
        profile.carbs_g        = int(request.POST.get('carbs_g', profile.carbs_g))
        profile.fat_g          = int(request.POST.get('fat_g', profile.fat_g))
        profile.save()
        messages.success(request, '✅ Diet profile updated!')
        return redirect('diet')

    return render(request, 'diet/edit_profile.html', {'profile': profile})