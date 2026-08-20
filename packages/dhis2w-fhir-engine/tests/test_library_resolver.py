"""Tests for CQL library resolution."""

from typing import Any

from dhis2w_fhir_engine.engine.cql import (
    CompositeLibraryResolver,
    CQLEvaluator,
    FileLibraryResolver,
    InMemoryLibraryResolver,
)


class TestInMemoryLibraryResolver:
    """Test in-memory library resolver."""

    def test_resolve_by_name(self) -> None:
        resolver = InMemoryLibraryResolver()
        resolver.add_library("TestLib", "library TestLib define X: 1")

        result = resolver.resolve("TestLib")
        assert result == "library TestLib define X: 1"

    def test_resolve_with_version(self) -> None:
        resolver = InMemoryLibraryResolver()
        resolver.add_library("TestLib", "library TestLib version '1.0' define X: 1", "1.0")
        resolver.add_library("TestLib", "library TestLib version '2.0' define X: 2", "2.0")

        result = resolver.resolve("TestLib", "1.0")
        assert result is not None
        assert "version '1.0'" in result

        result = resolver.resolve("TestLib", "2.0")
        assert result is not None
        assert "version '2.0'" in result

    def test_resolve_not_found(self) -> None:
        resolver = InMemoryLibraryResolver()
        result = resolver.resolve("NonExistent")
        assert result is None

    def test_init_with_libraries(self) -> None:
        resolver = InMemoryLibraryResolver({"MyLib": "library MyLib define Y: 2"})
        result = resolver.resolve("MyLib")
        assert result is not None


class TestFileLibraryResolver:
    """Test file-based library resolver."""

    def test_resolve_from_directory(self, tmp_path: Any) -> None:
        # Create a test library file
        lib_file = tmp_path / "MyHelpers.cql"
        lib_file.write_text("library MyHelpers define Double: 2 * 2")

        resolver = FileLibraryResolver([tmp_path])
        result = resolver.resolve("MyHelpers")

        assert result is not None
        assert "library MyHelpers" in result

    def test_resolve_with_version_pattern(self, tmp_path: Any) -> None:
        # Create versioned library file
        lib_file = tmp_path / "MyLib-1.0.cql"
        lib_file.write_text("library MyLib version '1.0' define X: 1")

        resolver = FileLibraryResolver([tmp_path])
        result = resolver.resolve("MyLib", "1.0")

        assert result is not None
        assert "version '1.0'" in result

    def test_resolve_from_subdirectory(self, tmp_path: Any) -> None:
        # Create library in subdirectory
        subdir = tmp_path / "FHIRHelpers"
        subdir.mkdir()
        lib_file = subdir / "FHIRHelpers.cql"
        lib_file.write_text("library FHIRHelpers define ToString: 'test'")

        resolver = FileLibraryResolver([tmp_path])
        result = resolver.resolve("FHIRHelpers")

        assert result is not None
        assert "library FHIRHelpers" in result

    def test_resolve_not_found(self, tmp_path: Any) -> None:
        resolver = FileLibraryResolver([tmp_path])
        result = resolver.resolve("NonExistent")
        assert result is None

    def test_add_search_path(self, tmp_path: Any) -> None:
        resolver = FileLibraryResolver()
        resolver.add_search_path(tmp_path)
        assert tmp_path in resolver.search_paths


class TestCompositeLibraryResolver:
    """Test composite resolver that chains multiple resolvers."""

    def test_resolve_from_first_resolver(self) -> None:
        mem1 = InMemoryLibraryResolver({"Lib1": "library Lib1 define X: 1"})
        mem2 = InMemoryLibraryResolver({"Lib2": "library Lib2 define Y: 2"})

        composite = CompositeLibraryResolver([mem1, mem2])

        result = composite.resolve("Lib1")
        assert result is not None
        assert "Lib1" in result

    def test_resolve_from_second_resolver(self) -> None:
        mem1 = InMemoryLibraryResolver({"Lib1": "library Lib1 define X: 1"})
        mem2 = InMemoryLibraryResolver({"Lib2": "library Lib2 define Y: 2"})

        composite = CompositeLibraryResolver([mem1, mem2])

        result = composite.resolve("Lib2")
        assert result is not None
        assert "Lib2" in result

    def test_first_match_wins(self) -> None:
        mem1 = InMemoryLibraryResolver({"Lib": "library Lib define X: 1"})
        mem2 = InMemoryLibraryResolver({"Lib": "library Lib define Y: 2"})

        composite = CompositeLibraryResolver([mem1, mem2])

        result = composite.resolve("Lib")
        assert result is not None
        assert "X: 1" in result  # First resolver wins

    def test_resolve_not_found(self) -> None:
        mem1 = InMemoryLibraryResolver({"Lib1": "library Lib1"})
        composite = CompositeLibraryResolver([mem1])

        result = composite.resolve("NonExistent")
        assert result is None


class TestEvaluatorWithResolver:
    """Test evaluator with library resolver integration."""

    def test_evaluator_with_library_paths(self, tmp_path: Any) -> None:
        # Create helper library
        helper_file = tmp_path / "MyHelpers.cql"
        helper_file.write_text("""
library MyHelpers version '1.0'

define function Double(x Integer):
    x * 2
""")

        # Create evaluator with library path
        evaluator = CQLEvaluator(library_paths=[tmp_path])

        # Load the helper library directly
        lib = evaluator.load_library("MyHelpers", "1.0")
        assert lib is not None
        assert lib.name == "MyHelpers"

    def test_evaluator_with_in_memory_resolver(self) -> None:
        resolver = InMemoryLibraryResolver()
        resolver.add_library(
            "Common",
            """
library Common version '1.0'

define Pi: 3.14159
define function Square(x Decimal): x * x
""",
        )

        evaluator = CQLEvaluator(library_resolver=resolver)

        # Load the library through the resolver
        lib = evaluator.load_library("Common", "1.0")
        assert lib is not None
        assert lib.name == "Common"
        assert "Pi" in lib.definitions

    def test_library_manager_resolve_includes(self, tmp_path: Any) -> None:
        # Create two libraries
        helper_file = tmp_path / "Helpers.cql"
        helper_file.write_text("""
library Helpers version '1.0'

define Pi: 3.14159
""")

        main_file = tmp_path / "Main.cql"
        main_file.write_text("""
library Main version '1.0'

include Helpers version '1.0'

define TwoPi: Helpers.Pi * 2
""")

        # Create evaluator with library path
        evaluator = CQLEvaluator(library_paths=[tmp_path])

        # Compile main library
        main_source = main_file.read_text()
        main_lib = evaluator.compile(main_source)

        assert main_lib.name == "Main"
        assert len(main_lib.includes) == 1
        assert main_lib.includes[0].library == "Helpers"

        # Resolve includes
        resolved = evaluator.library_manager.resolve_includes(main_lib)
        assert "Helpers" in resolved
        assert resolved["Helpers"].name == "Helpers"
