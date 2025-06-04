from django.db import models


class User(models.Model):
    contact = models.CharField(max_length=20)
    username = models.CharField(max_length=255)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return self.username

