import json
import multiprocessing
from multiprocessing.queues import Queue
from pathlib import Path
from tempfile import TemporaryDirectory

import whisperx
from whisperx.utils import get_writer

from common import ProcessEvent, get_output_dir, get_waiting_file
from config import Settings
from tasks.task import Task

from .base import BaseProvider, OnEventCallback


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

    def _handle_transcription(
        self,
        temp_dir: Path,
        waiting_audio: Path,
        event_queue: Queue[ProcessEvent],
    ) -> None:
        self._emit_log_event(event_queue, "transcription process start")

        self._emit_log_event(event_queue, "load transcription model")
        model = self._get_transcription_model()
        self._emit_log_event(event_queue, "transcription model loaded")

        self._emit_log_event(event_queue, "load transcription audio")
        audio = whisperx.load_audio(waiting_audio)
        self._emit_log_event(event_queue, "transcription audio loaded")

        self._emit_log_event(event_queue, "transcribe audio")
        result = model.transcribe(audio, batch_size=16)
        self._emit_log_event(event_queue, "audio transcribed")

        self._emit_log_event(event_queue, "write transcription result")
        writer = get_writer("json", str(temp_dir))
        writer(result, str(waiting_audio), {})
        self._emit_log_event(event_queue, "transcription result written")

    def _handle_alignment(
        self,
        temp_dir: Path,
        waiting_audio: Path,
        event_queue: Queue[ProcessEvent],
    ) -> None:
        self._emit_log_event(event_queue, "alignment process start")

        self._emit_log_event(event_queue, "load transcription result")
        transcription_path = temp_dir / f"{waiting_audio.stem}.json"
        with transcription_path.open(encoding="utf-8") as file:
            result = json.load(file)
        self._emit_log_event(event_queue, "transcription result loaded")

        language = result["language"]
        if result["segments"]:
            self._emit_log_event(event_queue, "load alignment model")
            model, metadata = self._get_align_model(language)
            self._emit_log_event(event_queue, "alignment model loaded")

            self._emit_log_event(event_queue, "load alignment audio")
            audio = whisperx.load_audio(waiting_audio)
            self._emit_log_event(event_queue, "alignment audio loaded")

            self._emit_log_event(event_queue, "align audio")
            result = whisperx.align(
                result["segments"],
                model,
                metadata,
                audio,
                self._get_device(),
                return_char_alignments=True,
            )
            self._emit_log_event(event_queue, "audio aligned")

        result["language"] = language

        self._emit_log_event(event_queue, "output result")
        self.output(result, waiting_audio)
        self._emit_log_event(event_queue, "result written")

    def run(
        self,
        task: Task,
        on_event: OnEventCallback,
    ) -> None:
        waiting_audio = get_waiting_file(task.filename)
        if not waiting_audio.is_file():
            raise FileNotFoundError(f"Task audio not found: {task.filename}")

        mp_ctx = multiprocessing.get_context("spawn")
        with TemporaryDirectory(prefix=f"{self._settings.app_name}-") as temp_dir:
            temp_dir = Path(temp_dir)

            self._run_process(
                mp_ctx,
                "Transcription",
                self._handle_transcription,
                on_event,
                args=(temp_dir, waiting_audio),
            )

            self._run_process(
                mp_ctx,
                "Alignment",
                self._handle_alignment,
                on_event,
                args=(temp_dir, waiting_audio),

            )

    @staticmethod
    def output(result: dict, audio_path: Path) -> None:
        chars = []
        segments = []

        for segment in result.get("segments", []):
            segment_chars = [
                {
                    "start": char.get("start"),
                    "end": char.get("end"),
                    "score": char.get("score"),
                    "char": char.get("word", ""),
                }
                for char in segment.get("words", [])
            ]
            score = (
                sum(char["score"] or 0 for char in segment_chars)
                / len(segment_chars)
                if segment_chars
                else 0
            )

            chars.extend(segment_chars)
            segments.append(
                {
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "text": segment.get("text", ""),
                    "chars": segment_chars,
                    "score": score,
                }
            )

        output_path = get_output_dir() / f"{audio_path.stem}.json"
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "language": result.get("language", ""),
                    "text": "".join(segment["text"] for segment in segments),
                    "chars": chars,
                    "segments": segments,
                },
                file,
                ensure_ascii=False,
            )
