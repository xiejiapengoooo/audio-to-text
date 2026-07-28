import json
import multiprocessing
from multiprocessing.queues import Queue
from pathlib import Path
from tempfile import TemporaryDirectory

import whisperx

from common import ProcessEvent, get_output_file
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
        transcription_temporary_file: Path,
        waiting_file: Path,
        event_queue: Queue[ProcessEvent],
    ) -> None:
        self._emit_log_event(event_queue, "transcription process start")

        self._emit_log_event(event_queue, "load transcription model")
        model = self._get_transcription_model()
        self._emit_log_event(event_queue, "transcription model loaded")

        self._emit_log_event(event_queue, "load transcription audio")
        audio = whisperx.load_audio(waiting_file)
        self._emit_log_event(event_queue, "transcription audio loaded")

        self._emit_log_event(event_queue, "transcribe audio")
        result = model.transcribe(audio, batch_size=16)
        self._emit_log_event(event_queue, "audio transcribed")

        self._emit_log_event(event_queue, "write transcription result")
        with transcription_temporary_file.open("w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False)
        self._emit_log_event(event_queue, "transcription result written")

    def _handle_alignment(
        self,
        transcription_temporary_file: Path,
        waiting_file: Path,
        temporary_output_path: Path,
        event_queue: Queue[ProcessEvent],
    ) -> None:
        self._emit_log_event(event_queue, "alignment process start")

        self._emit_log_event(event_queue, "load transcription result")
        with transcription_temporary_file.open(encoding="utf-8") as file:
            result = json.load(file)
        self._emit_log_event(event_queue, "transcription result loaded")

        language = result["language"]
        if result["segments"]:
            self._emit_log_event(event_queue, "load alignment model")
            model, metadata = self._get_align_model(language)
            self._emit_log_event(event_queue, "alignment model loaded")

            self._emit_log_event(event_queue, "load alignment audio")
            audio = whisperx.load_audio(waiting_file)
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
        self.output(result, temporary_output_path)
        self._emit_log_event(event_queue, "result written")

    def run(
        self,
        task: Task,
        on_event: OnEventCallback,
    ) -> None:
        task.raise_if_cancelled()

        waiting_file = task.filepath
        if not waiting_file.is_file():
            raise FileNotFoundError(f"Task audio not found: {task.filename}")

        mp_ctx = multiprocessing.get_context("spawn")
        output_path = get_output_file(f"{waiting_file.stem}.json")
        temporary_output_path = get_output_file(f".{task.task_id}.tmp")
        try:
            with TemporaryDirectory(prefix=f"{self._settings.app_name}-") as temp_dir:
                transcription_temporary_file = Path(temp_dir) / f"{waiting_file.stem}.json"

                self._run_process(
                    mp_ctx,
                    "Transcription",
                    task,
                    self._handle_transcription,
                    on_event,
                    args=(transcription_temporary_file, waiting_file),
                )

                self._run_process(
                    mp_ctx,
                    "Alignment",
                    task,
                    self._handle_alignment,
                    on_event,
                    args=(transcription_temporary_file, waiting_file, temporary_output_path),
                )

                task.raise_if_cancelled()

                def commit_output() -> None:
                    temporary_output_path.replace(output_path)

                task.commit(commit_output)
        finally:
            try:
                temporary_output_path.unlink(missing_ok=True)
            except OSError:
                self._logger.exception(
                    "Failed to remove temporary output for task %s",
                    task.task_id,
                )

    @staticmethod
    def output(result: dict, output_path: Path) -> None:
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
