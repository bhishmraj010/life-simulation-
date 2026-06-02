from django.db import models
from django.conf import settings
from django.utils import timezone


PRIORITY_POINTS = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}
SKIP_DEDUCTION  = 3
LOSE_PUNISHMENT = 10


class Task(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('completed', 'Completed'),
        ('skipped',   'Skipped'),
    ]

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks')
    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority    = models.IntegerField(default=3, choices=[(i, i) for i in range(1, 6)])
    quality     = models.IntegerField(null=True, blank=True)  # 1–10, unlocked at Level 3
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    due_date    = models.DateField(default=timezone.now)
    order       = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-priority', 'created_at']

    def __str__(self):
        return f"{self.title} ({self.priority}★)"

    def get_points(self):
        base = PRIORITY_POINTS.get(self.priority, 6)
        if self.quality is not None:
            if self.quality >= 7:
                base += 5
            elif self.quality <= 3:
                base -= 5
        return base

    def stars(self):
        return '★' * self.priority + '☆' * (5 - self.priority)


class DailyLog(models.Model):
    STATUS_CHOICES = [
        ('win',     'Day Win'),
        ('survive', 'Day Survive'),
        ('lose',    'Day Lose'),
        ('ongoing', 'Ongoing'),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_logs')
    date         = models.DateField(default=timezone.now)
    total_points = models.IntegerField(default=0)
    day_status   = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ongoing')
    streak       = models.IntegerField(default=0)
    punishment   = models.BooleanField(default=False)
    # Store thresholds used that day
    win_threshold     = models.IntegerField(default=40)
    survive_threshold = models.IntegerField(default=20)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.user} | {self.date} | {self.total_points}pts | {self.day_status}"

    def calculate_status(self):
        if self.total_points >= self.win_threshold:
            return 'win'
        elif self.total_points >= self.survive_threshold:
            return 'survive'
        else:
            return 'lose'

    def save(self, *args, **kwargs):
        self.day_status = self.calculate_status()
        super().save(*args, **kwargs)