"""
Tests für das Ninko TTS-System (Piper TTS).

Testet:
- VoiceManager (mit Mock-Verzeichnisstruktur)
- PiperService.synthesize() (mit gemocktem Subprocess)
- audio_utils (wav_to_ogg, wav_to_mp3, ogg_to_wav) via Mock
- Telegram Voice-Reply-Flow (Mock: sendVoice API + TTS)
- Teams Voice-Reply-Flow (Mock: Bot-Framework + TTS)

Ausführen:
    python backend/test_tts.py
"""

import asyncio
import os
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_minimal_wav(sample_rate: int = 22050, duration_ms: int = 100) -> bytes:
    """Erzeugt ein minimales, gültiges WAV-Byte-Objekt für Tests."""
    import struct
    num_samples = int(sample_rate * duration_ms / 1000)
    audio_data = b"\x00\x00" * num_samples  # Stille
    data_size = len(audio_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,       # PCM chunk size
        1,        # PCM format
        1,        # Mono
        sample_rate,
        sample_rate * 2,
        2,        # Block align
        16,       # Bits per sample
        b"data",
        data_size,
    )
    return header + audio_data


def _create_mock_voices_dir(tmp_path: Path) -> Path:
    """Erstellt eine Mock-Stimmenstruktur für Tests."""
    voice_dir = tmp_path / "de" / "thorsten-medium"
    voice_dir.mkdir(parents=True)
    onnx_file = voice_dir / "de_DE-thorsten-medium.onnx"
    json_file = voice_dir / "de_DE-thorsten-medium.onnx.json"
    onnx_file.write_bytes(b"mock onnx model data")
    json_file.write_text('{"sample_rate": 22050, "num_speakers": 1}')
    return tmp_path


# ── VoiceManager Tests ────────────────────────────────────────────────────────

class TestVoiceManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.voices_dir = _create_mock_voices_dir(Path(self.tmp))

    def test_list_languages(self):
        from core.tts.voice_manager import VoiceManager
        vm = VoiceManager(voices_dir=self.voices_dir)
        langs = vm.list_languages()
        self.assertIn("de", langs)

    def test_list_voices(self):
        from core.tts.voice_manager import VoiceManager
        vm = VoiceManager(voices_dir=self.voices_dir)
        voices = vm.list_voices("de")
        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].name, "thorsten-medium")
        self.assertEqual(voices[0].lang, "de")

    def test_get_voice_path_success(self):
        from core.tts.voice_manager import VoiceManager
        vm = VoiceManager(voices_dir=self.voices_dir)
        path = vm.get_voice_path("de", "thorsten-medium")
        self.assertTrue(path.exists())
        self.assertTrue(str(path).endswith(".onnx"))

    def test_get_voice_path_missing_lang(self):
        from core.tts.voice_manager import VoiceManager
        vm = VoiceManager(voices_dir=self.voices_dir)
        with self.assertRaises(FileNotFoundError):
            vm.get_voice_path("en", "some-voice")

    def test_get_voice_path_missing_voice(self):
        from core.tts.voice_manager import VoiceManager
        vm = VoiceManager(voices_dir=self.voices_dir)
        with self.assertRaises(FileNotFoundError):
            vm.get_voice_path("de", "nonexistent-voice")

    def test_empty_voices_dir(self):
        from core.tts.voice_manager import VoiceManager
        vm = VoiceManager(voices_dir="/nonexistent/path")
        self.assertEqual(vm.list_languages(), [])

    def test_no_config_json_skipped(self):
        """Stimmen ohne .onnx.json werden nicht gelistet."""
        from core.tts.voice_manager import VoiceManager
        # Erstelle .onnx ohne .onnx.json
        broken_dir = Path(self.tmp) / "de" / "broken-voice"
        broken_dir.mkdir(parents=True, exist_ok=True)
        (broken_dir / "broken.onnx").write_bytes(b"data")
        # kein .onnx.json
        vm = VoiceManager(voices_dir=Path(self.tmp))
        voices = vm.list_voices("de")
        names = [v.name for v in voices]
        self.assertNotIn("broken-voice", names)


# ── PiperService Tests ────────────────────────────────────────────────────────

class TestPiperService(unittest.TestCase):

    def test_binary_not_found_raises(self):
        """Wenn Piper-Binary nicht gefunden wird, muss PiperError geworfen werden."""
        from core.tts.piper_service import PiperError, PiperService
        with self.assertRaises(PiperError):
            PiperService(piper_binary="/nonexistent/piper")

    def test_synthesize_success(self):
        """Erfolgreiche Synthese: gemockter Subprocess, echte WAV-Ausgabe."""
        from core.tts.piper_service import PiperService

        wav_bytes = _make_minimal_wav()

        # Mock: shutil.which gibt Pfad zurück, Subprocess schreibt WAV in Temp-Datei
        with patch("core.tts.piper_service.shutil.which", return_value="/usr/local/bin/piper"):
            service = PiperService(piper_binary="piper")

        async def run():
            with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
                model_path = Path(f.name)
                f.write(b"mock model")

            try:
                # Mock create_subprocess_exec
                mock_proc = AsyncMock()
                mock_proc.returncode = 0
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))

                async def mock_exec(*args, **kwargs):
                    # Temp output file schreiben
                    output_file = next(
                        (args[i + 1] for i, a in enumerate(args) if a == "--output_file"),
                        None,
                    )
                    if output_file:
                        with open(output_file, "wb") as f:
                            f.write(wav_bytes)
                    return mock_proc

                with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
                    result = await service.synthesize("Hallo Welt", model_path)

                self.assertEqual(result, wav_bytes)
            finally:
                model_path.unlink(missing_ok=True)

        asyncio.run(run())

    def test_synthesize_model_not_found(self):
        """Fehler wenn Modell-Datei nicht existiert."""
        from core.tts.piper_service import PiperError, PiperService

        with patch("core.tts.piper_service.shutil.which", return_value="/usr/bin/piper"):
            service = PiperService(piper_binary="piper")

        async def run():
            with self.assertRaises(PiperError):
                await service.synthesize("Test", Path("/nonexistent/model.onnx"))

        asyncio.run(run())

    def test_synthesize_piper_error_exit(self):
        """PiperError wenn Piper mit Fehler-Exit beendet."""
        from core.tts.piper_service import PiperError, PiperService

        with patch("core.tts.piper_service.shutil.which", return_value="/usr/bin/piper"):
            service = PiperService(piper_binary="piper")

        async def run():
            with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
                model_path = Path(f.name)
            try:
                mock_proc = AsyncMock()
                mock_proc.returncode = 1
                mock_proc.communicate = AsyncMock(return_value=(b"", b"model not found"))

                with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                    with self.assertRaises(PiperError):
                        await service.synthesize("Test", model_path)
            finally:
                model_path.unlink(missing_ok=True)

        asyncio.run(run())


# ── audio_utils Tests ─────────────────────────────────────────────────────────

class TestAudioUtils(unittest.TestCase):

    def _mock_ffmpeg(self, output_bytes: bytes):
        """Gibt einen Mock-Kontext zurück, der ffmpeg simuliert."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0

        async def _communicate():
            return b"", b""

        mock_proc.communicate = _communicate

        async def mock_exec(*args, **kwargs):
            # Ausgabedatei schreiben (letztes Argument)
            out_path = args[-1]
            with open(out_path, "wb") as f:
                f.write(output_bytes)
            return mock_proc

        return patch("asyncio.create_subprocess_exec", side_effect=mock_exec)

    def test_wav_to_ogg(self):
        from core.tts.audio_utils import wav_to_ogg
        wav = _make_minimal_wav()
        fake_ogg = b"OggS\x00" + b"\x00" * 100

        async def run():
            with patch("core.tts.audio_utils.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self._mock_ffmpeg(fake_ogg):
                    result = await wav_to_ogg(wav)
            self.assertEqual(result, fake_ogg)

        asyncio.run(run())

    def test_wav_to_mp3(self):
        from core.tts.audio_utils import wav_to_mp3
        wav = _make_minimal_wav()
        fake_mp3 = b"\xff\xfb" + b"\x00" * 100  # MP3-Magic-Bytes

        async def run():
            with patch("core.tts.audio_utils.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self._mock_ffmpeg(fake_mp3):
                    result = await wav_to_mp3(wav)
            self.assertEqual(result, fake_mp3)

        asyncio.run(run())

    def test_ogg_to_wav(self):
        from core.tts.audio_utils import ogg_to_wav
        fake_ogg = b"OggS\x00" + b"\x00" * 50
        expected_wav = _make_minimal_wav(16000)

        async def run():
            with patch("core.tts.audio_utils.shutil.which", return_value="/usr/bin/ffmpeg"):
                with self._mock_ffmpeg(expected_wav):
                    result = await ogg_to_wav(fake_ogg)
            self.assertEqual(result, expected_wav)

        asyncio.run(run())

    def test_ffmpeg_not_found(self):
        from core.tts.audio_utils import wav_to_ogg

        async def run():
            with patch("core.tts.audio_utils.shutil.which", return_value=None):
                with self.assertRaises(RuntimeError):
                    await wav_to_ogg(b"data")

        asyncio.run(run())


# ── Telegram Voice-Reply-Flow Tests ──────────────────────────────────────────

class TestTelegramVoiceReply(unittest.IsolatedAsyncioTestCase):

    async def _make_bot(self):
        """Erstellt TelegramBot mit gemockter FastAPI-App."""
        app = MagicMock()
        app.state.orchestrator = AsyncMock()
        app.state.orchestrator.route = AsyncMock(
            return_value=("Hallo, das ist die Antwort!", "test_module", False)
        )
        from modules.telegram.bot import TelegramBot
        return TelegramBot(app)

    async def test_voice_message_sets_is_voice_flag(self):
        """Eingehende Voice-Nachricht setzt is_voice=True."""
        bot = await self._make_bot()

        update = {
            "update_id": 1,
            "message": {
                "chat": {"id": 123},
                "voice": {"file_id": "ABC123", "duration": 5},
            },
        }

        with patch.object(bot, "_transcribe_voice", return_value="Hallo Bot") as mock_trans, \
             patch.object(bot, "_send", return_value=True), \
             patch.object(bot, "_keep_typing", return_value=asyncio.sleep(0)), \
             patch.object(bot, "get_token", return_value="test_token"), \
             patch("modules.telegram.bot.get_redis") as mock_redis, \
             patch("modules.telegram.bot.ConnectionManager") as mock_conn_mgr:

            mock_conn = MagicMock()
            mock_conn.config = {
                "allowed_chat_ids": "",
                "voice_reply": "true",
                "voice_reply_text_too": "false",
            }
            mock_conn_mgr.get_default_connection = AsyncMock(return_value=mock_conn)

            mock_redis_inst = AsyncMock()
            mock_redis_inst.get_chat_history = AsyncMock(return_value=[])
            mock_redis_inst.store_chat_message = AsyncMock()
            mock_redis.return_value = mock_redis_inst

            with patch.object(bot, "_send_voice_reply", new_callable=AsyncMock) as mock_voice_reply:
                await bot.handle_update(update, "test_token")
                # Voice-Reply wurde aufgerufen
                mock_voice_reply.assert_called_once()
                # Transkription wurde aufgerufen
                mock_trans.assert_called_once_with("ABC123", "test_token")

    async def test_text_message_no_voice_reply(self):
        """Textnachrichten lösen keinen Voice-Reply aus."""
        bot = await self._make_bot()

        update = {
            "update_id": 2,
            "message": {
                "chat": {"id": 456},
                "text": "Hallo Bot",
            },
        }

        with patch.object(bot, "_send", return_value=True), \
             patch.object(bot, "_keep_typing", return_value=asyncio.sleep(0)), \
             patch("modules.telegram.bot.get_redis") as mock_redis, \
             patch("modules.telegram.bot.ConnectionManager") as mock_conn_mgr:

            mock_conn = MagicMock()
            mock_conn.config = {"allowed_chat_ids": "", "voice_reply": "true"}
            mock_conn_mgr.get_default_connection = AsyncMock(return_value=mock_conn)

            mock_redis_inst = AsyncMock()
            mock_redis_inst.get_chat_history = AsyncMock(return_value=[])
            mock_redis_inst.store_chat_message = AsyncMock()
            mock_redis.return_value = mock_redis_inst

            with patch.object(bot, "_send_voice_reply", new_callable=AsyncMock) as mock_voice_reply:
                await bot.handle_update(update, "test_token")
                # Kein Voice-Reply bei Textnachricht
                mock_voice_reply.assert_not_called()

    async def test_send_voice_reply_tts_error_does_not_crash(self):
        """TTS-Fehler beim Voice-Reply propagiert nicht nach oben."""
        bot = await self._make_bot()

        with patch("modules.telegram.bot.synthesize_reply", side_effect=RuntimeError("TTS nicht verfügbar")):
            # Darf keine Exception werfen
            await bot._send_voice_reply("token", 123, "Test")


# ── Teams Voice-Reply-Flow Tests ──────────────────────────────────────────────

class TestTeamsVoiceReply(unittest.IsolatedAsyncioTestCase):

    async def test_audio_attachment_sets_is_voice(self):
        """Audio-Anhang in Teams-Activity setzt is_voice=True."""
        from fastapi import FastAPI
        app = MagicMock(spec=FastAPI)
        app.state.orchestrator = AsyncMock()
        app.state.orchestrator.route = AsyncMock(
            return_value=("Antwort vom Agenten.", None, False)
        )

        activity = {
            "type": "message",
            "serviceUrl": "https://smba.trafficmanager.net/de/",
            "conversation": {"id": "conv_123"},
            "id": "act_456",
            "from": {"id": "user_789", "name": "Testuser"},
            "text": "",
            "attachments": [
                {
                    "contentType": "audio/ogg",
                    "contentUrl": "https://example.com/voice.ogg",
                    "name": "voice.ogg",
                }
            ],
        }

        with patch("modules.teams.bot.ConnectionManager") as mock_conn_mgr, \
             patch("modules.teams.bot.get_redis") as mock_redis, \
             patch("modules.teams.bot._transcribe_teams_attachment", return_value="Transkribierter Text"), \
             patch("modules.teams.bot.send_teams_message", new_callable=AsyncMock), \
             patch("modules.teams.bot._send_teams_voice_reply", new_callable=AsyncMock) as mock_voice:

            mock_conn = MagicMock()
            mock_conn.config = {
                "allowed_user_ids": "",
                "voice_reply": "true",
                "voice_reply_text_too": "true",
            }
            mock_conn_mgr.get_default_connection = AsyncMock(return_value=mock_conn)

            mock_redis_inst = AsyncMock()
            mock_redis_inst.get_chat_history = AsyncMock(return_value=[])
            mock_redis_inst.store_chat_message = AsyncMock()
            mock_redis_inst.connection = AsyncMock()
            mock_redis_inst.connection.set = AsyncMock()
            mock_redis.return_value = mock_redis_inst

            from modules.teams.bot import handle_teams_turn
            await handle_teams_turn(app, activity)

            mock_voice.assert_called_once()

    async def test_send_teams_voice_reply_tts_error(self):
        """TTS-Fehler beim Teams Voice-Reply propagiert nicht nach oben."""
        with patch("modules.teams.bot.synthesize_reply", side_effect=Exception("Piper fehlt")):
            from modules.teams.bot import _send_teams_voice_reply
            # Darf keine Exception werfen
            await _send_teams_voice_reply("https://example.com", "conv", "act", "Text")


# ── is_tts_available Tests ────────────────────────────────────────────────────

class TestTtsAvailability(unittest.TestCase):

    def test_tts_disabled_returns_false(self):
        """is_tts_available() gibt False zurück wenn TTS_ENABLED=false."""
        with patch("core.tts.get_settings") as mock_settings:
            mock_cfg = MagicMock()
            mock_cfg.TTS_ENABLED = False
            mock_settings.return_value = mock_cfg

            from core.tts import is_tts_available
            # Modul-Level _service zurücksetzen
            import core.tts as tts_module
            tts_module._service = None

            result = is_tts_available()
            self.assertFalse(result)

    def test_tts_enabled_no_binary(self):
        """is_tts_available() gibt False zurück wenn Binary fehlt."""
        import core.tts as tts_module
        tts_module._service = None

        with patch("core.tts.get_settings") as mock_settings, \
             patch("core.tts.piper_service.shutil.which", return_value=None):
            mock_cfg = MagicMock()
            mock_cfg.TTS_ENABLED = True
            mock_cfg.PIPER_BINARY = "nonexistent_piper"
            mock_settings.return_value = mock_cfg

            from core.tts import is_tts_available
            result = is_tts_available()
            self.assertFalse(result)


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Ninko TTS Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
