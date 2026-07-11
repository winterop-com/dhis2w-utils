# Auth providers

Every auth method implements the same `AuthProvider` Protocol (`headers()` + `refresh_if_needed()`), so the rest of the client is identical regardless of what you pick.

## The Protocol

::: dhis2w_client.v42.auth.base

## Basic

::: dhis2w_client.v42.auth.basic

## Personal Access Token

::: dhis2w_client.v42.auth.pat

## OAuth2 / OIDC

::: dhis2w_client.v42.auth.oauth2

## Session cookie

::: dhis2w_client.v42.auth.session
