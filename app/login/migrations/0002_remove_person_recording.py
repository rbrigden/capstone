# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2019-03-01 20:22
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('login', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='person',
            name='recording',
        ),
    ]
