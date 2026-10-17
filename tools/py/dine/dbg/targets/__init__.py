from .fake import FakeTarget
from .ios import IosTarget

TARGETS = {t.name: t for t in (FakeTarget, IosTarget)}
