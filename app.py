import json
import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory

import whisperx
import torch
from whisperx.utils import get_writer
from .config import get_settings
from .logger import get_logger


settings = get_settings()


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_compute_type():
    return "float16" if torch.cuda.is_available() else "int8"


def get_transcription_model():
    return whisperx.load_model(
        settings.model_name,
        device=get_device(),
        compute_type=get_compute_type(),
        download_root=str(settings.model_download_dir) if settings.model_download_dir else None,
        local_files_only=bool(settings.model_download_dir),
    )


def get_align_model(language_code: str):
    return whisperx.load_align_model(
        language_code=language_code,
        device=get_device(),
        model_dir=str(settings.model_download_dir) if settings.model_download_dir else None,
        model_cache_only=bool(settings.model_download_dir),
    )


def get_waiting_dir():
    settings.waiting_dir.mkdir(parents=True, exist_ok=True)
    return settings.waiting_dir


def get_waiting_audio():
    waiting_audio = (path for path in get_waiting_dir().iterdir() if path.is_file())
    return min(
        waiting_audio,
        key=lambda path: (path.stat().st_ctime_ns, path.name),
        default=None,
    )


def get_output_dir():
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    return settings.output_dir


def handle_transcription(temp_dir: Path, waiting_audio: Path):
    logger = get_logger("Transcription")

    logger.info("transcription process start")

    logger.info("load transcription model")
    model = get_transcription_model()
    logger.info("transcription model loaded")

    logger.info("load audio")
    audio = whisperx.load_audio(waiting_audio)
    logger.info("audio loaded")

    logger.info("transcribe audio")
    result = model.transcribe(audio, batch_size=16)
    logger.info("audio transcribed")

    logger.info("write result")
    writer = get_writer("json", str(temp_dir))
    writer(result, str(waiting_audio), {})
    logger.info("result written")


def handle_alignment(temp_dir: Path, waiting_audio: Path):
    logger = get_logger("Alignment")

    logger.info("alignment process start")

    logger.info("load transcription result")
    transcription_path = temp_dir / f"{waiting_audio.stem}.json"
    with transcription_path.open(encoding="utf-8") as file:
        result = json.load(file)
    logger.info("transcription result loaded")

    language = result["language"]
    if result["segments"]:
        logger.info("load alignment model")
        model, metadata = get_align_model(language)
        logger.info("alignment model loaded")

        logger.info("load audio")
        audio = whisperx.load_audio(waiting_audio)
        logger.info("audio loaded")

        logger.info("align audio")
        result = whisperx.align(
            result["segments"],
            model,
            metadata,
            audio,
            get_device(),
            return_char_alignments=False,
        )
        logger.info("audio aligned")

    result["language"] = language

    logger.info("output result")
    writer = get_writer("json", str(get_output_dir()))
    writer(result, str(waiting_audio), {})
    logger.info("result written")


def run_process(ctx, target, name, args=()):
    process = ctx.Process(target=target, name=name, args=args)

    try:
        process.start()
        process.join()

        if process.exitcode != 0:
            raise RuntimeError(
                f"{name} exit failed，exitcode={process.exitcode}"
            )
    finally:
        if process.is_alive():
            process.terminate()
            process.join()

        process.close()


def main():
    mp_ctx = multiprocessing.get_context("spawn")
    waiting_audio = get_waiting_audio()
    if waiting_audio is None:
        get_logger("Main").info("waiting audio is empty")
        return

    with TemporaryDirectory(prefix=f"{settings.app_name}-") as temp_dir:
        temp_dir = Path(temp_dir)

        run_process(
            mp_ctx,
            handle_transcription,
            "Transcription",
            args=(temp_dir, waiting_audio),
        )

        run_process(
            mp_ctx,
            handle_alignment,
            "Alignment",
            args=(temp_dir, waiting_audio),
        )



if __name__ == "__main__":
    main()
