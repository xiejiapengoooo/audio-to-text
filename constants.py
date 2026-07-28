from enum import StrEnum

from common import Model, OutputFileType

DEFAULT_MODEL: Model = "whisperx"
DEFAULT_OUTPUT_FILE_TYPE: OutputFileType = "json"

class ProcessEventType(StrEnum):
   LOG = "log"
