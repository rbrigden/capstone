# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2019-03-02 21:29
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('login', '0002_remove_person_recording'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='recording',
            field=models.FileField(null=True, upload_to=b''),
        ),
    ]