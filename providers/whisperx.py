import json
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
import whisperx
from whisperx.utils import get_writer
from config import Settings
from .base import BaseProvider


class WhisperXProvider(BaseProvider):
    model_name="large-v3"

    def __init__(self, settings: Settings):
        super().__init__("WhisperX", settings)

    def _get_transcription_model(self):
        return whisperx.load_model(
            self.model_name,
            device=self._get_device(),
            compute_type=self._get_compute_type(),
            download_root=str(self._settings.model_download_dir) if self._settings.model_download_dir else None,
            local_files_only=bool(self._settings.model_download_dir),
        )

    def _get_align_model(self, language_code: str):
        return whisperx.load_align_model(
            language_code=language_code,
            device=self._get_device(),
            model_dir=str(self._settings.model_download_dir) if self._settings.model_download_dir else None,
            model_cache_only=bool(self._settings.model_download_dir),
        )

    def _handle_transcription(self, temp_dir: Path, waiting_audio: Path):
        self._logger.info("transcription process start")

        self._logger.info("load transcription model")
        model = self._get_transcription_model()
        self._logger.info("transcription model loaded")

        self._logger.info("load transcription audio")
        audio = whisperx.load_audio(waiting_audio)
        self._logger.info("transcription audio loaded")

        self._logger.info("transcribe audio")
        result = model.transcribe(audio, batch_size=16)
        self._logger.info("audio transcribed")

        self._logger.info("write transcription result")
        writer = get_writer("json", str(temp_dir))
        writer(result, str(waiting_audio), {})
        self._logger.info("transcription result written")

    def _handle_alignment(self, temp_dir: Path, waiting_audio: Path):
        self._logger.info("alignment process start")

        self._logger.info("load transcription result")
        transcription_path = temp_dir / f"{waiting_audio.stem}.json"
        with transcription_path.open(encoding="utf-8") as file:
            result = json.load(file)
        self._logger.info("transcription result loaded")

        language = result["language"]
        if result["segments"]:
            self._logger.info("load alignment model")
            model, metadata = self._get_align_model(language)
            self._logger.info("alignment model loaded")

            self._logger.info("load alignment audio")
            audio = whisperx.load_audio(waiting_audio)
            self._logger.info("alignment audio loaded")

            self._logger.info("align audio")
            result = whisperx.align(
                result["segments"],
                model,
                metadata,
                audio,
                self._get_device(),
                return_char_alignments=False,
            )
            self._logger.info("audio aligned")

        result["language"] = language

        self._logger.info("output result")
        writer = get_writer("json", str(self._get_output_dir()))
        writer(result, str(waiting_audio), {})
        self._logger.info("result written")

    def run(self):
      mp_ctx = multiprocessing.get_context("spawn")
      waiting_audio = self._get_waiting_audio()
      if waiting_audio is None:
          self._logger.info("waiting audio is empty")
          return

      with TemporaryDirectory(prefix=f"{self._settings.app_name}-") as temp_dir:
          temp_dir = Path(temp_dir)

          self._run_process(
              mp_ctx,
              self._handle_transcription,
              "Transcription",
              args=(temp_dir, waiting_audio),
          )

          self._run_process(
              mp_ctx,
              self._handle_alignment,
              "Alignment",
              args=(temp_dir, waiting_audio),
          )
