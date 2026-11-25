"""The AI behind Lumi's chat, chosen in Settings. Each provider's SDK is imported only when it's the chosen one."""
import ipaddress
from urllib.parse import urlsplit

from .base import Declined, ToolCall  # noqa: F401  (used by chat.py)

LOOPBACK_NAMES = {'localhost'}


def is_loopback(host):
    """True only for this PC itself: localhost, 127.x.x.x or ::1. "localhost.example.com" is somewhere else."""
    host = (host or '').strip('[]').lower().rstrip('.')
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_custom_url(url):
    """None if the address is safe to send messages (and a key) to, otherwise the reason for the user.
    Anything off this PC must use https://, so nobody on the network can read or change the conversation."""
    try:
        parts = urlsplit((url or '').strip())
        host, port = parts.hostname, parts.port  # .port raises ValueError for a bad port
    except ValueError:
        return 'That address isn\'t valid.'
    if parts.scheme not in ('http', 'https') or not host:
        return 'Enter a URL starting with https:// (or http://localhost for a model on this PC).'
    if parts.username or parts.password or '@' in parts.netloc:
        return 'Leave the user name and password out of the address; Lumi sends the key separately.'
    if parts.fragment:
        return 'Remove the # part from the address.'
    if parts.scheme == 'http' and not is_loopback(host):
        return 'A server on another computer must use https://, so your messages and key are encrypted.'
    return None


def describe_custom_url(url):
    """Where the custom server is, in words, for the privacy notice."""
    try:
        host = urlsplit(url or '').hostname
    except ValueError:
        host = None
    return 'your own model on this PC' if is_loopback(host) else 'the server at ' + (host or 'an unknown address')

# label, config key for its model, whether it needs a key, whether it can do live voice, and model suggestions
PROVIDERS = {
    'gemini': {'label': 'Gemini', 'model_key': 'gemini_model', 'needs_key': True, 'live': True,
               'models': ['gemini-3.5-flash', 'gemini-3.8-flash', 'gemini-3.5-flash-lite']},
    'claude': {'label': 'Claude', 'model_key': 'claude_model', 'needs_key': True, 'live': False,
               'models': ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5']},
    'openai': {'label': 'OpenAI', 'model_key': 'openai_model', 'needs_key': True, 'live': False,
               'models': ['gpt-5-mini', 'gpt-5']},
    'custom': {'label': 'Other (OpenAI-compatible)', 'model_key': 'custom_model', 'needs_key': False, 'live': False,
               'models': ['llama3.2', 'qwen2.5']},
}
PACKAGES = {'gemini': 'google-genai', 'claude': 'anthropic', 'openai': 'openai', 'custom': 'openai'}


def chosen(config):
    name = config.get('ai_provider')
    return name if name in PROVIDERS else 'gemini'


def create(config, api_key):
    """Builds the chosen provider. Returns (provider, None) or (None, a message for the user)."""
    name = chosen(config)
    info = PROVIDERS[name]
    model = config.get(info['model_key'])
    if info['needs_key'] and not api_key and name != 'claude':  # Claude's SDK can also use a signed-in profile
        return None, f"Add your {info['label']} API key in Settings so I can chat!"
    try:
        if name == 'gemini':
            from .gemini import GeminiProvider
            return GeminiProvider(model, api_key, backup=config.get('gemini_backup_model')), None
        if name == 'claude':
            from .claude import ClaudeProvider
            return ClaudeProvider(model, api_key), None
        from .openai_compat import OpenAICompatibleProvider
        if name == 'openai':
            return OpenAICompatibleProvider(model, api_key), None
        problem = check_custom_url(config.get('custom_url'))  # config.json can be edited by hand, so check here too
        if problem:
            return None, problem + ' Fix the server address in Settings.'
        return OpenAICompatibleProvider(model, api_key, base_url=config.get('custom_url'), label='your model'), None
    except ImportError:
        return None, f"Install {PACKAGES[name]} so I can chat!"
    except Exception as e:
        print(f"AI Init Error ({name}): {e}")
        if name == 'claude' and not api_key:
            return None, "Add your Claude API key in Settings so I can chat!"
        return None, f"I couldn't connect to {info['label']}."
