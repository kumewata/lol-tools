"""Errors raised by lol_coach. Messages never contain tokens."""

from __future__ import annotations


class CoachError(Exception):
    """Base class; `str(e)` is safe to show to the user."""


class ReauthRequired(CoachError):
    """Sign-in is missing, expired beyond refresh, or was revoked."""


class LoginFailed(CoachError):
    """The browser sign-in did not complete."""


class PlanScopeNotGranted(CoachError):
    """The user signed in but did not grant ChatGPT plan usage."""


class NotEligible(CoachError):
    """The ChatGPT account or workspace cannot use plan sharing."""


class UsageLimitExceeded(CoachError):
    """The per-app or plan usage limit was reached."""


class UnsupportedRequest(CoachError):
    """The model, input or parameter is not supported for plan usage."""


class TemporarilyUnavailable(CoachError):
    """OpenAI could not check usage right now (retryable)."""


class InferenceFailed(CoachError):
    """The response stream failed or ended without `response.completed`."""
