import asyncio
import base64
import threading
import time

from .system import SystemHelpers

# Media keys, used when Windows reports no media session
MEDIA_KEYS = {'play': 0xB3, 'next': 0xB0, 'prev': 0xB1}


class MediaWatcher:
    """Follows Windows' current media session (any app that shows in the volume flyout) and reports changes."""

    def __init__(self, on_change):
        self._on_change = on_change
        self._loop = None
        self._session = None
        self._last = None
        self._art_key = None
        self._art = None
        self.state = {'active': False}

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        except ImportError:
            print("Media Info Unavailable: install winrt-Windows.Media.Control")
            return
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._poll(Manager))

    async def _poll(self, Manager):
        manager = await Manager.request_async()
        while True:
            try:
                await self._refresh(manager)
            except Exception as e:
                print(f"Media Info Error: {e}")
            await asyncio.sleep(1)

    async def _refresh(self, manager):
        session = manager.get_current_session()
        self._session = session
        if not session:
            state = {'active': False}
        else:
            props = await session.try_get_media_properties_async()
            info = session.get_playback_info()
            PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
            key = (props.title, props.artist)
            if key != self._art_key:
                self._art_key = key
                self._art = await self._read_art(props.thumbnail)
            state = {
                'active': bool(props.title),
                'title': props.title or '',
                'artist': props.artist or '',
                'app': _app_name(session.source_app_user_model_id),
                'playing': info.playback_status == PLAYING,
                'art': self._art,
            }
        if state != self._last:
            self._last = state
            self.state = state
            self._on_change(state)

    @staticmethod
    async def _read_art(thumbnail):
        # Artwork arrives as a stream; send it to the page as a small data URI
        if thumbnail is None:
            return None
        try:
            from winrt.windows.storage.streams import Buffer, InputStreamOptions
            stream = await thumbnail.open_read_async()
            size = min(stream.size, 2_000_000)
            buffer = Buffer(size)
            await stream.read_async(buffer, size, InputStreamOptions.READ_AHEAD)
            data = bytes(memoryview(buffer))[:buffer.length]
            mime = 'image/png' if data[:4] == b'\x89PNG' else 'image/jpeg'
            return f'data:{mime};base64,' + base64.b64encode(data).decode()
        except Exception as e:
            print(f"Media Artwork Error: {e}")
            return None

    def control(self, action, wait=2.0):
        """action: 'play', 'pause', 'toggle', 'next' or 'prev'. Waits (briefly) for the app's answer and returns
        'ok' (the app accepted it), 'already' (play when playing, pause when paused: nothing done), 'nothing'
        (no media to pause), 'sent' (only a keyboard media key could be pressed, so the result is unknown) or
        'failed', or 'unchanged' (the app said yes but is still paused or playing). Play and pause are never sent as a toggle, so pause can't start paused music."""
        session = self._session
        if action in ('play', 'pause') and self.state.get('active'):
            if self.state.get('playing') == (action == 'play'):
                return 'already'
        if session is None or self._loop is None:
            if action == 'pause' and not self.state.get('playing'):
                return 'nothing'  # the only key is play/pause, which would start something
            key = MEDIA_KEYS.get('play' if action in ('play', 'pause', 'toggle') else action)
            if key is None:
                return 'failed'
            SystemHelpers.send_key(key)
            return 'sent'
        calls = {'play': session.try_play_async, 'pause': session.try_pause_async,
                 'toggle': session.try_toggle_play_pause_async, 'next': session.try_skip_next_async,
                 'prev': session.try_skip_previous_async}
        if action not in calls:
            return 'failed'
        future = asyncio.run_coroutine_threadsafe(self._press(calls[action], action), self._loop)
        try:
            outcome = future.result(wait)
        except Exception as e:  # the app took too long to answer
            print(f"Media Control Error ({action}): {type(e).__name__}: {e}")
            return 'sent'
        if outcome == 'ok' and action in ('play', 'pause'):
            return self._confirm(action == 'play')
        return outcome

    def _confirm(self, playing, wait=2.2):
        """Some apps say yes and then don't change (a Netflix tab in the background, say). The watcher re-reads the
        session every second, so give it a moment to show the new state before calling it done."""
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if bool(self.state.get('playing')) == playing:
                return 'ok'
            time.sleep(0.1)
        return 'unchanged'

    async def _press(self, start, action):
        try:
            return 'ok' if await start() else 'failed'
        except Exception as e:
            print(f"Media Control Error ({action}): {e}")
            if action in ('next', 'prev', 'toggle'):
                SystemHelpers.send_key(MEDIA_KEYS['play' if action == 'toggle' else action])  # the media keys still work
                return 'sent'
            return 'failed'


def _app_name(app_id):
    # "Spotify.exe" -> "Spotify"; "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic" -> "ZuneMusic"
    name = (app_id or '').split('!')[-1].split('\\')[-1]
    name = name.rsplit('.', 1)[-1] if '.' in name and not name.lower().endswith('.exe') else name
    return name[:-4] if name.lower().endswith('.exe') else name
