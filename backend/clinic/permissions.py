"""Role-based access. The server is the authority; the UI only hides what it can't do.

admin        superuser / staff
doctor       any user linked to a Doctor row (sees only their own patients)
receptionist member of the "receptionist" group
Anyone else is authenticated but has no role, and is refused everywhere.
"""
from rest_framework.permissions import BasePermission

ADMIN, DOCTOR, RECEPTIONIST = "admin", "doctor", "receptionist"


def role_of(user):
    if not user.is_authenticated:
        return None
    if not hasattr(user, "_role_cache"):
        if user.is_superuser or user.is_staff:
            role = ADMIN
        elif hasattr(user, "doctor"):  # reverse one-to-one; missing row => False
            role = DOCTOR
        elif user.groups.filter(name=RECEPTIONIST).exists():
            role = RECEPTIONIST
        else:
            role = None
        user._role_cache = role
    return user._role_cache


def doctor_id_of(user):
    doctor = getattr(user, "doctor", None)
    return doctor.pk if doctor else None


class HasRole(BasePermission):
    """Views declare `roles` as a tuple, or a dict keyed by HTTP method."""
    message = "Your role is not allowed to do this."

    def has_permission(self, request, view):
        roles = view.roles
        if isinstance(roles, dict):
            roles = roles.get(request.method, ())
        return role_of(request.user) in roles
