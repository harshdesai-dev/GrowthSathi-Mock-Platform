from django.core.files.storage import Storage


class DisabledMediaStorage(Storage):
    """Question images are external URLs; never persist uploads on an ephemeral host."""

    def _open(self, name, mode="rb"):
        raise NotImplementedError("Production media uploads are not configured.")

    def _save(self, name, content):
        raise NotImplementedError("Production media uploads are not configured.")

    def exists(self, name):
        raise NotImplementedError("Production media uploads are not configured.")
