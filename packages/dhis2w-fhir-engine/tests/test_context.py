"""Tests for EvaluationContext."""

from datetime import datetime
from typing import Any

from dhis2w_fhir_engine.engine.context import EvaluationContext


class TestEvaluationContextBasics:
    """Tests for basic EvaluationContext functionality."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        ctx = EvaluationContext()
        assert ctx.resource is None
        assert ctx.root_resource is None
        assert ctx.model is None
        assert ctx.now is None
        assert ctx.reference_resolver is None

    def test_init_with_resource(self) -> None:
        """Test initialization with resource."""
        resource = {"resourceType": "Patient", "id": "123"}
        ctx = EvaluationContext(resource=resource)
        assert ctx.resource == resource
        assert ctx.root_resource == resource  # Defaults to resource

    def test_init_with_root_resource(self) -> None:
        """Test initialization with separate root resource."""
        resource = {"resourceType": "Observation"}
        root = {"resourceType": "Patient"}
        ctx = EvaluationContext(resource=resource, root_resource=root)
        assert ctx.resource == resource
        assert ctx.root_resource == root

    def test_init_with_now(self) -> None:
        """Test initialization with fixed datetime."""
        fixed_time = datetime(2024, 3, 15, 10, 30)
        ctx = EvaluationContext(now=fixed_time)
        assert ctx.now == fixed_time


class TestThisStack:
    """Tests for $this variable stack."""

    def test_this_empty_returns_none(self) -> None:
        """Test $this returns None when stack is empty."""
        ctx = EvaluationContext()
        assert ctx.this is None

    def test_push_and_pop_this(self) -> None:
        """Test pushing and popping $this."""
        ctx = EvaluationContext()
        ctx.push_this("value1")
        assert ctx.this == "value1"
        ctx.push_this("value2")
        assert ctx.this == "value2"
        result = ctx.pop_this()
        assert result == "value2"
        assert ctx.this == "value1"

    def test_pop_empty_returns_none(self) -> None:
        """Test popping from empty stack returns None."""
        ctx = EvaluationContext()
        assert ctx.pop_this() is None


class TestIndexStack:
    """Tests for $index variable stack."""

    def test_index_empty_returns_none(self) -> None:
        """Test $index returns None when stack is empty."""
        ctx = EvaluationContext()
        assert ctx.index is None

    def test_push_and_pop_index(self) -> None:
        """Test pushing and popping $index."""
        ctx = EvaluationContext()
        ctx.push_index(0)
        assert ctx.index == 0
        ctx.push_index(5)
        assert ctx.index == 5
        result = ctx.pop_index()
        assert result == 5
        assert ctx.index == 0

    def test_pop_empty_index_returns_none(self) -> None:
        """Test popping from empty index stack returns None."""
        ctx = EvaluationContext()
        assert ctx.pop_index() is None


class TestTotalStack:
    """Tests for $total variable stack."""

    def test_total_empty_returns_none(self) -> None:
        """Test $total returns None when stack is empty."""
        ctx = EvaluationContext()
        assert ctx.total is None

    def test_push_and_pop_total(self) -> None:
        """Test pushing and popping $total."""
        ctx = EvaluationContext()
        ctx.push_total(100)
        assert ctx.total == 100
        ctx.push_total(200)
        assert ctx.total == 200
        result = ctx.pop_total()
        assert result == 200
        assert ctx.total == 100

    def test_pop_empty_total_returns_none(self) -> None:
        """Test popping from empty total stack returns None."""
        ctx = EvaluationContext()
        assert ctx.pop_total() is None


class TestConstants:
    """Tests for external constants (%name)."""

    def test_set_and_get_constant(self) -> None:
        """Test setting and getting a constant."""
        ctx = EvaluationContext()
        ctx.set_constant("myVar", 42)
        assert ctx.get_constant("myVar") == 42

    def test_get_unknown_constant_returns_none(self) -> None:
        """Test getting unknown constant returns None."""
        ctx = EvaluationContext()
        assert ctx.get_constant("unknown") is None

    def test_get_resource_constant(self) -> None:
        """Test %resource returns the current resource."""
        resource = {"resourceType": "Patient"}
        ctx = EvaluationContext(resource=resource)
        assert ctx.get_constant("resource") == resource

    def test_get_root_resource_constant(self) -> None:
        """Test %rootResource returns the root resource."""
        root = {"resourceType": "Bundle"}
        ctx = EvaluationContext(resource={"entry": []}, root_resource=root)
        assert ctx.get_constant("rootResource") == root

    def test_get_context_constant(self) -> None:
        """Test %context returns the resource (default context)."""
        resource = {"resourceType": "Patient"}
        ctx = EvaluationContext(resource=resource)
        assert ctx.get_constant("context") == resource


class TestFunctionOverrides:
    """Tests for custom function overrides."""

    def test_register_function(self) -> Any:
        """Test registering a custom function."""
        ctx = EvaluationContext()

        def custom_func(ctx: EvaluationContext, collection: list[Any]) -> list[Any]:
            return [len(collection)]

        ctx.register_function("myFunc", custom_func)
        override = ctx.get_function_override("myFunc")
        assert override is not None
        assert override(ctx, [1, 2, 3]) == [3]

    def test_get_unknown_override_returns_none(self) -> None:
        """Test getting unknown override returns None."""
        ctx = EvaluationContext()
        assert ctx.get_function_override("unknown") is None


class TestChildContext:
    """Tests for child context creation."""

    def test_child_inherits_root_resource(self) -> None:
        """Test child context inherits root resource."""
        root = {"resourceType": "Bundle"}
        ctx = EvaluationContext(resource=root, root_resource=root)
        child = ctx.child()
        assert child.root_resource == root

    def test_child_with_new_resource(self) -> None:
        """Test child context with new resource."""
        root = {"resourceType": "Bundle"}
        ctx = EvaluationContext(resource=root, root_resource=root)
        new_resource = {"resourceType": "Patient"}
        child = ctx.child(resource=new_resource)
        assert child.resource == new_resource
        assert child.root_resource == root

    def test_child_inherits_constants(self) -> None:
        """Test child context inherits constants."""
        ctx = EvaluationContext()
        ctx.set_constant("myVar", 42)
        child = ctx.child()
        assert child.get_constant("myVar") == 42

    def test_child_inherits_function_overrides(self) -> None:
        """Test child context inherits function overrides."""
        ctx = EvaluationContext()
        ctx.register_function("myFunc", lambda c, col: col)
        child = ctx.child()
        assert child.get_function_override("myFunc") is not None

    def test_child_inherits_now(self) -> None:
        """Test child context inherits now."""
        fixed_time = datetime(2024, 3, 15)
        ctx = EvaluationContext(now=fixed_time)
        child = ctx.child()
        assert child.now == fixed_time

    def test_child_inherits_reference_resolver(self) -> Any:
        """Test child context inherits reference resolver."""

        def resolver(ref: str) -> dict[str, str]:
            return {"id": "resolved"}

        ctx = EvaluationContext(reference_resolver=resolver)
        child = ctx.child()
        assert child.reference_resolver is resolver

    def test_child_constants_independent(self) -> None:
        """Test modifying child constants doesn't affect parent."""
        ctx = EvaluationContext()
        ctx.set_constant("shared", "parent")
        child = ctx.child()
        child.set_constant("shared", "child")
        child.set_constant("new", "value")
        assert ctx.get_constant("shared") == "parent"
        assert ctx.get_constant("new") is None

    def test_child_function_overrides_independent(self) -> None:
        """Test modifying child overrides doesn't affect parent."""
        ctx = EvaluationContext()
        ctx.register_function("shared", lambda c, col: "parent")
        child = ctx.child()
        child.register_function("shared", lambda c, col: "child")
        # Parent should still have original
        parent_fn = ctx.get_function_override("shared")
        child_fn = child.get_function_override("shared")
        assert parent_fn is not None
        assert child_fn is not None
        assert parent_fn(None, None) == "parent"
        assert child_fn(None, None) == "child"
