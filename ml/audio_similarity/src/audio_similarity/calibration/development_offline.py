"""Explicit offline Hub transport for local cached-model extraction."""
import httpx
from huggingface_hub import set_client_factory
from huggingface_hub.errors import OfflineModeIsEnabled


def offline_request(request):
    raise OfflineModeIsEnabled('Calibration model loading is local-cache-only')


def offline_client():
    # A mock transport cannot make a socket request. Ignore inherited proxies
    # without changing the environment of Gemini or the acquisition worker.
    return httpx.Client(transport=httpx.MockTransport(offline_request), trust_env=False)


def configure():
    set_client_factory(offline_client)
