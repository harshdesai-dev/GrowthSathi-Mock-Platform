from rest_framework.permissions import BasePermission


class IsActiveOwner(BasePermission):
    """Allow only active accounts with both Django owner flags."""

    message = "Owner access is required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
            and user.is_superuser
        )
