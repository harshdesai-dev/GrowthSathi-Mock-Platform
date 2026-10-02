from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StudentProfile, User


@receiver(post_save, sender=User)
def create_student_profile(sender, instance: User, created: bool, **kwargs) -> None:
    if created:
        StudentProfile.objects.create(user=instance, full_name=instance.get_full_name())
