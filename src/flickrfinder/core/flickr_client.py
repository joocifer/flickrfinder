from __future__ import annotations

import flickrapi

from flickrfinder.config import Config


class NotAuthenticated(RuntimeError):
    pass


def build_client(cfg: Config, *, require_auth: bool = True) -> flickrapi.FlickrAPI:
    """Build a Flickr client. flickrapi caches the OAuth token on disk."""
    flickr = flickrapi.FlickrAPI(
        cfg.api_key,
        cfg.api_secret,
        format="parsed-json",
    )
    if require_auth and flickr.token_cache.token is None:
        raise NotAuthenticated("No saved Flickr token. Run `flickrfinder auth` first.")
    return flickr


def do_oauth_flow(cfg: Config) -> dict[str, str]:
    """Run the OAuth 1.0a dance and persist the token via flickrapi's cache."""
    flickr = flickrapi.FlickrAPI(
        cfg.api_key,
        cfg.api_secret,
        format="parsed-json",
    )
    flickr.get_request_token(oauth_callback="oob")
    auth_url = flickr.auth_url(perms="read")
    print(f"\nOpen this URL in your browser to authorize flickrfinder:\n\n  {auth_url}\n")
    verifier = input("After approving, paste the verifier code shown by Flickr: ").strip()
    flickr.get_access_token(verifier)
    tok = flickr.token_cache.token
    return {
        "user_nsid": tok.user_nsid,
        "username": tok.username,
    }


def clear_saved_token(cfg: Config) -> None:
    """Forget the cached token by overwriting it with nothing."""
    flickr = flickrapi.FlickrAPI(cfg.api_key, cfg.api_secret, format="parsed-json")
    flickr.token_cache.forget()
