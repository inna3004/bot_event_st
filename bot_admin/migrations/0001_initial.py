# Generated by Django 5.2.1 on 2025-05-31 05:03

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contact', models.CharField(max_length=20)),
                ('username', models.CharField(max_length=255)),
                ('is_admin', models.BooleanField(default=False)),
            ],
        ),
    ]
