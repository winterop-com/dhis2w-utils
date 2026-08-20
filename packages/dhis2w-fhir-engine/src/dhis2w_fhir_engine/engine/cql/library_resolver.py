"""CQL Library Resolution.

This module provides resolvers for loading CQL library sources by name and version.
Supports multiple resolution strategies that can be chained together.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class LibraryResolver(ABC):
    """Abstract base class for library resolvers.

    Library resolvers are responsible for finding and loading CQL library
    source code given a library name and optional version.
    """

    @abstractmethod
    def resolve(self, name: str, version: str | None = None) -> str | None:
        """Resolve a library name to its source code.

        Args:
            name: The library name (e.g., 'FHIRHelpers')
            version: Optional version string (e.g., '4.0.1')

        Returns:
            The library source code as a string, or None if not found
        """
        pass


class FileLibraryResolver(LibraryResolver):
    """Resolves libraries from the filesystem.

    Searches for library files in configured directories using multiple
    naming patterns:
    - {name}.cql
    - {name}-{version}.cql
    - {name}/{name}.cql
    - {name}/{name}-{version}.cql
    """

    def __init__(self, search_paths: list[Path | str] | None = None) -> None:
        """Initialize the file resolver.

        Args:
            search_paths: List of directories to search for libraries.
                         Defaults to current directory if not specified.
        """
        self.search_paths: list[Path] = []
        if search_paths:
            for path in search_paths:
                p = Path(path) if isinstance(path, str) else path
                if p.exists() and p.is_dir():
                    self.search_paths.append(p)
        if not self.search_paths:
            self.search_paths = [Path.cwd()]

    def add_search_path(self, path: Path | str) -> None:
        """Add a directory to the search path.

        Args:
            path: Directory path to add
        """
        p = Path(path) if isinstance(path, str) else path
        if p.exists() and p.is_dir() and p not in self.search_paths:
            self.search_paths.append(p)

    def resolve(self, name: str, version: str | None = None) -> str | None:
        """Resolve a library from the filesystem.

        Searches all configured directories for files matching the library
        name and version patterns.

        Args:
            name: Library name (e.g., 'FHIRHelpers')
            version: Optional version (e.g., '4.0.1')

        Returns:
            Library source code or None if not found
        """
        # Generate candidate filenames
        candidates: list[str] = []

        # Pattern 1: {name}.cql
        candidates.append(f"{name}.cql")

        # Pattern 2: {name}-{version}.cql (if version provided)
        if version:
            candidates.append(f"{name}-{version}.cql")

        # Pattern 3: lowercase versions
        candidates.append(f"{name.lower()}.cql")
        if version:
            candidates.append(f"{name.lower()}-{version}.cql")

        # Search in all paths
        for search_path in self.search_paths:
            # Try direct file patterns
            for candidate in candidates:
                file_path = search_path / candidate
                if file_path.exists() and file_path.is_file():
                    return file_path.read_text(encoding="utf-8")

            # Pattern 4: {name}/{name}.cql (subdirectory)
            subdir = search_path / name
            if subdir.exists() and subdir.is_dir():
                for candidate in candidates:
                    file_path = subdir / candidate
                    if file_path.exists() and file_path.is_file():
                        return file_path.read_text(encoding="utf-8")

                # Also try just the name in the subdir
                file_path = subdir / f"{name}.cql"
                if file_path.exists() and file_path.is_file():
                    return file_path.read_text(encoding="utf-8")

        return None


class InMemoryLibraryResolver(LibraryResolver):
    """Resolves libraries from an in-memory dictionary.

    Useful for testing or when libraries are provided programmatically.
    """

    def __init__(self, libraries: dict[str, str] | None = None) -> None:
        """Initialize the in-memory resolver.

        Args:
            libraries: Dictionary mapping library names to source code.
                      Keys can be 'name' or 'name|version' format.
        """
        self._libraries: dict[str, str] = {}
        if libraries:
            self._libraries.update(libraries)

    def add_library(self, name: str, source: str, version: str | None = None) -> None:
        """Add a library to the resolver.

        Args:
            name: Library name
            source: Library source code
            version: Optional version
        """
        key = f"{name}|{version}" if version else name
        self._libraries[key] = source
        # Also add without version for fallback
        if version and name not in self._libraries:
            self._libraries[name] = source

    def resolve(self, name: str, version: str | None = None) -> str | None:
        """Resolve a library from memory.

        Args:
            name: Library name
            version: Optional version

        Returns:
            Library source code or None if not found
        """
        # Try exact match with version
        if version:
            key = f"{name}|{version}"
            if key in self._libraries:
                return self._libraries[key]

        # Fall back to name only
        return self._libraries.get(name)


class CompositeLibraryResolver(LibraryResolver):
    """Chains multiple resolvers together.

    Tries each resolver in order until one returns a result.
    """

    def __init__(self, resolvers: list[LibraryResolver] | None = None) -> None:
        """Initialize the composite resolver.

        Args:
            resolvers: List of resolvers to chain
        """
        self._resolvers: list[LibraryResolver] = resolvers or []

    def add_resolver(self, resolver: LibraryResolver) -> None:
        """Add a resolver to the chain.

        Args:
            resolver: Resolver to add
        """
        self._resolvers.append(resolver)

    def resolve(self, name: str, version: str | None = None) -> str | None:
        """Resolve a library by trying each resolver in order.

        Args:
            name: Library name
            version: Optional version

        Returns:
            Library source code from the first successful resolver, or None
        """
        for resolver in self._resolvers:
            result = resolver.resolve(name, version)
            if result is not None:
                return result
        return None
