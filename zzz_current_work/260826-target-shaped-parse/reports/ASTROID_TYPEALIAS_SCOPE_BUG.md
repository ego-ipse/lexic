# astroid: a `type` statement's type parameters leak into the enclosing scope

**Component:** astroid (`astroid/rebuilder.py`, `astroid/nodes/node_classes.py::TypeAlias`)
**Affects:** astroid 4.0.4 (installed), and `main` as of 2026-09-03 — `TypeAlias`
is still `AssignTypeNode + Statement`, not a scoped node.
**Visible through:** pylint 4.0.8 `W0621 redefined-outer-name` on every generic
function or class in a module that also declares a PEP 695 `type` alias with the
same parameter name.
**Python:** 3.12+ (`type` statement); reproduced on 3.14.3.

## Minimal reproduction

```python
# probe.py
type Alias[Carry] = list[Carry]


def free[Carry](value: Carry) -> Carry:
    return value
```

```
$ pylint probe.py
probe.py:4:9: W0621: Redefining name 'Carry' from outer scope (line 1) (redefined-outer-name)
```

```python
>>> import astroid
>>> m = astroid.parse(open("probe.py").read())
>>> sorted(m.locals)
['Alias', 'Carry', 'free']          # 'Carry' should not be a module local
>>> m.body[0].type_params[0].name.scope()
<Module l.0 at ...>                  # the alias's parameter is scoped to the Module
```

The interpreter disagrees:

```python
>>> import importlib.util
>>> spec = importlib.util.spec_from_file_location("probe", "probe.py")
>>> mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
>>> "Carry" in vars(mod)
False
>>> mod.Alias.__type_params__
(Carry,)
```

## Expected

PEP 695 gives a `type` statement its own annotation scope. Its type parameters
are bound in that scope only; they are not names of the enclosing module,
class or function. `Module.locals` must not contain `Carry`, and a function
or class declaring its own `[Carry]` parameter does not redefine anything.

## Actual

astroid registers the alias's parameter as a local of the enclosing scope.
Any later generic function or class using the same parameter name is then
reported by pylint as shadowing a module-level name.

## Root cause

`TreeRebuilder.visit_typealias` visits each type parameter with
`visit_typevar`, which creates the parameter's `AssignName` via
`visit_assignname`. `AssignName` is registered with `set_local` on
`node.scope()`. For a parameter of a `ClassDef` or `FunctionDef` that scope is
the class or function itself, because both are `LocalsDictNodeNG` subclasses,
so their parameters land in their own `locals` (verified: `Rec[Carry]` and
`free[Carry]` put `Carry` in the class's and function's locals). `TypeAlias`
is **not** a `LocalsDictNodeNG`: `node.scope()` for its parameter walks up to
the enclosing `Module`, and the parameter is registered there.

```
TypeAlias.__mro__  -> (TypeAlias, AssignTypeNode, Statement, NodeNG)
ClassDef.__mro__   -> (ClassDef, FilterStmtsBaseNode, LocalsDictNodeNG, LookupMixIn, Statement, ...)
```

So the defect is the missing scope on `TypeAlias`, not the visitor: the
visitor does the right thing for the two scoped owners and the wrong thing for
the one unscoped owner.

## Suggested fix

Give `TypeAlias` an annotation scope for its parameters, mirroring how
`ClassDef`/`FunctionDef` own their `type_params`:

- make `TypeAlias` a `LocalsDictNodeNG` (with its own `locals`), or introduce
  a dedicated scoped node for the alias's parameter scope so that
  `AssignName.scope()` for a type parameter resolves to the alias;
- ensure name lookup from the alias's `value` expression (`list[Carry]`)
  resolves `Carry` in that scope, then falls through to the enclosing scope
  for everything else, matching the runtime's lazy evaluation;
- `Module.locals` (and any enclosing class/function `locals`) no longer
  receive the parameter.

Nothing changes for `ClassDef`/`FunctionDef` parameters, which are already
correct.

## Regression test

```python
def test_type_alias_params_do_not_leak_into_enclosing_scope():
    module = astroid.parse(
        """
        type Alias[Carry] = list[Carry]
        def free[Carry](value: Carry) -> Carry:
            return value
        """
    )
    assert "Carry" not in module.locals
    alias = module.body[0]
    assert alias.type_params[0].name.scope() is not module
    assert "Carry" in module.body[1].locals  # the function's own parameter, unchanged
```

And the pylint side, once astroid is fixed: the probe above yields no
`W0621`, while a genuine module-level `Carry = 1` followed by
`def free[Carry](...)` still does.

---

# Second defect: generic NamedTuple members are missing on a generic function's return

**Component:** astroid brain for `typing.NamedTuple` (the inference tip that
supplies `_replace`, `_make`, `_fields`, `_asdict`).
**Affects:** astroid 4.0.4 with pylint 4.0.8; the direct-instance case is
resolved in 4.0.8, the returned-instance case is not.
**Visible through:** pylint `E1101 no-member`.

## Minimal reproduction

```python
from typing import NamedTuple


class Two[T, U](NamedTuple):
    a: T
    b: U


def make[T, U](x: T, y: U) -> Two[T, U]:
    return Two(x, y)


def direct() -> None:
    print(Two(1, "a")._replace(a=2))       # no finding


def via_return() -> None:
    print(make(1, "a")._replace(a=2))      # E1101: Instance of 'Two' has no '_replace' member
```

## Expected

Both calls are the same method on the same class; `Two` is a `NamedTuple`
subclass regardless of how its instance is reached.

## Actual

When the instance is inferred through a generic function's return
annotation `Two[T, U]`, the named-tuple brain's inference tip does not fire,
so the class is inferred without the members `typing.NamedTuple`
synthesises, and pylint reports `_replace` as missing. A direct construction
in the same module is inferred correctly.

## Suggested fix

Bind the synthesised members on the `ClassDef` itself when the class is a
`NamedTuple` subclass (the brain already knows this at class-build time),
rather than only supplying them through the instance inference tip; then
every inference path that reaches the class, including one through a
generic return type, sees them. A guard must key on the `NamedTuple` base,
not on the presence of `type_params`, or a generic class that is not a named
tuple would receive `_replace` too.

## Regression test

```python
def test_generic_namedtuple_members_through_generic_return():
    module = astroid.parse(
        """
        from typing import NamedTuple
        class Two[T, U](NamedTuple):
            a: T
            b: U
        def make[T, U](x: T, y: U) -> Two[T, U]:
            return Two(x, y)
        make(1, "a")._replace(a=2)
        """
    )
    call = module.body[-1].value            # the _replace(...) call
    inferred = next(call.func.expr.infer()) # make(1, "a")
    assert "_replace" in inferred.getattr_names() if hasattr(inferred, "getattr_names") else inferred.getattr("_replace")
```

