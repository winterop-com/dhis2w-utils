"""Exceptions for FHIRPath/CQL evaluation."""


class FHIRPathError(Exception):
    """Base exception for FHIRPath evaluation errors."""

    pass


class FHIRPathTypeError(FHIRPathError):
    """Type error during FHIRPath evaluation."""

    pass


class FHIRPathSyntaxError(FHIRPathError):
    """Syntax error in FHIRPath expression."""

    pass


class CQLError(FHIRPathError):
    """Base exception for CQL evaluation errors."""

    pass
