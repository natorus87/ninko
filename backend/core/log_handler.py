import json
import logging
import threading
import queue
import asyncio
import datetime
from typing import Optional, List


REDIS_LOG_KEY = "ninko:logs"
MAX_LOG_ENTRIES = 10000

_CATEGORY_MAP = {
    "ninko.agents": "agent",
    "ninko.workflow": "workflow",
    "ninko.modules": "module",
    "ninko.api.logs": "system",
    "ninko.api": "system",
    "ninko.llm": "llm",
    "ninko": "system",
}

def _guess_category(logger_name: str) -> str:
    for prefix, cat in _CATEGORY_MAP.items():
        if logger_name.startswith(prefix):
            return cat
    return "system"

def _normalize_level(levelno: int) -> str:
    if levelno >= logging.CRITICAL: return "CRIT"
    if levelno >= logging.ERROR: return "ERROR"
    if levelno >= logging.WARNING: return "WARN"
    return "INFO"


class RedisLogHandler(logging.Handler):
    """
    Thread-sicherer Redis-Logging-Handler mit Background-Worker.
    Verhindert Blockaden und Probleme mit verschiedenen Event-Loops.
    """

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self._queue = queue.Queue(maxsize=2000)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True, name="RedisLogWorker")
        self._worker_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        # Rekursions-Schutz
        if getattr(record, "_redis_logged", False):
            return
        
        try:
            setattr(record, "_redis_logged", True)
            
            # Basis-Daten extrahieren
            try:
                msg = record.getMessage()
            except:
                msg = str(record.msg)
            
            entry = {
                "timestamp": datetime.datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp_unix": getattr(record, "created", 0),
                "level": _normalize_level(record.levelno),
                "logger": record.name,
                "category": _guess_category(record.name),
                "source": getattr(record, "source", ""),
                "message": msg,
            }
            
            if record.exc_info:
                try:
                    import traceback
                    entry["traceback"] = "".join(traceback.format_exception(*record.exc_info))
                except:
                    pass

            serialized = json.dumps(entry, ensure_ascii=False)
            
            try:
                self._queue.put_nowait(serialized)
            except queue.Full:
                pass # Queue voll -> logs verwerfen
            
        except Exception as e:
            try:
                import os
                err = f"!!! RedisLogHandler CRASH: {type(e).__name__}: {e} !!!\n"
                os.write(1, err.encode())
            except:
                pass
            self.handleError(record)

    def _worker(self):
        """Hintergrund-Thread für den Redis-Upload."""
        # Da aioredis async ist, brauchen wir hier einen eigenen Loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def _upload_loop():
            import redis.asyncio as aioredis
            from core.config import get_settings
            
            settings = get_settings()
            redis_conn = None
            
            logging.getLogger("ninko.log_handler").debug("RedisLogWorker started.")
            
            while not self._stop_event.is_set():
                try:
                    # Batch-Processing für Effizienz
                    batch = []
                    try:
                        # Warte max 1 Sekunde auf neue Logs
                        batch.append(self._queue.get(timeout=1.0))
                        # Versuche weitere 49 Logs ohne Warten mitzunehmen
                        for _ in range(49):
                            batch.append(self._queue.get_nowait())
                    except queue.Empty:
                        if not batch: continue

                    if redis_conn is None:
                        try:
                            # Eigene Connection für diesen Thread
                            redis_conn = aioredis.from_url(
                                settings.REDIS_URL,
                                decode_responses=True,
                                encoding="utf-8",
                            )
                        except Exception as e:
                            logging.getLogger("ninko.log_handler").error("RedisLogWorker redis init error: %s", e)
                            await asyncio.sleep(2)
                            continue

                    # Pipeline für Batch-Upload
                    try:
                        async with redis_conn.pipeline() as pipe:
                            for item in batch:
                                pipe.lpush(REDIS_LOG_KEY, item)
                            pipe.ltrim(REDIS_LOG_KEY, 0, MAX_LOG_ENTRIES - 1)
                            await pipe.execute()
                    except Exception as e:
                        logging.getLogger("ninko.log_handler").error("RedisLogWorker push error: %s", e)
                        redis_conn = None  # Reconnect beim nächsten Mal
                        await asyncio.sleep(2)
                        continue

                    for _ in range(len(batch)):
                        self._queue.task_done()

                except Exception as e:
                    logging.getLogger("ninko.log_handler").error("RedisLogWorker loop error: %s", e)
                    await asyncio.sleep(5)

            if redis_conn:
                await redis_conn.aclose()

        loop.run_until_complete(_upload_loop())

    def close(self):
        self._stop_event.set()
        super().close()
