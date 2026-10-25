from .fake import FakeTarget
from .gtk import GtkTarget
from .ios import IosTarget

TARGETS = {t.name: t for t in (FakeTarget, GtkTarget, IosTarget)}
