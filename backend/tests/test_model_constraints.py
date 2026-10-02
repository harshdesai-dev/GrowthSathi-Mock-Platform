import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User


@pytest.mark.django_db
def test_user_email_is_database_unique():
    User.objects.create_user(email="student@example.com", google_sub="first-sub")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="student@example.com", google_sub="second-sub")


@pytest.mark.django_db
def test_google_subject_is_database_unique():
    User.objects.create_user(email="first@example.com", google_sub="same-sub")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="second@example.com", google_sub="same-sub")
