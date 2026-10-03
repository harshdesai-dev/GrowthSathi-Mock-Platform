"""Process-local abuse guards; edge limits and trusted proxy verification are still required."""

from rest_framework.throttling import SimpleRateThrottle


class IdentityThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        identity = request.user.pk if request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": identity}


class LoginThrottle(IdentityThrottle):
    scope, rate = "google_login", "120/min"


class SessionThrottle(IdentityThrottle):
    scope, rate = "session", "300/min"


class ReadThrottle(IdentityThrottle):
    scope, rate = "read", "120/min"


class OrderThrottle(IdentityThrottle):
    scope, rate = "order", "10/min"


class VerifyThrottle(IdentityThrottle):
    scope, rate = "payment_verify", "30/min"


class StartThrottle(IdentityThrottle):
    scope, rate = "attempt_start", "20/min"
