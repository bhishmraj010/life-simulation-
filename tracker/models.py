from django.db import models
from django.conf import settings
from django.utils import timezone


WILLPOWER_POINTS = 7
WILLPOWER_DEDUCT = 7


class WillpowerTask(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('skipped',   'Skipped'),
    ]

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='willpower_tasks')
    title      = models.CharField(max_length=200)
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    due_date   = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user} | {self.title} | {self.status}"

    def get_points(self):
        if self.status == 'completed':
            return +WILLPOWER_POINTS
        elif self.status == 'skipped':
            return -WILLPOWER_DEDUCT
        return 0


class MealEntry(models.Model):
    MEAL_CHOICES = [
        ('breakfast', 'Breakfast'),
        ('lunch',     'Lunch'),
        ('dinner',    'Dinner'),
        ('snack',     'Snack'),
    ]

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='meal_entries')
    date        = models.DateField(default=timezone.now)
    meal_type   = models.CharField(max_length=10, choices=MEAL_CHOICES)
    description = models.TextField()
    is_healthy  = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', 'meal_type']

    def __str__(self):
        return f"{self.user} | {self.date} | {self.meal_type}"