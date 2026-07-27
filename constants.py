from enum import StrEnum
from common import Model


DEFAULT_MODEL: Model = "whisperx"

class ProcessEventType(StrEnum):
   LOG = "log"
