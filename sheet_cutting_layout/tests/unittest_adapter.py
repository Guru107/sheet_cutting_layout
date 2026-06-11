from __future__ import annotations

import inspect
import re
from contextlib import AbstractContextManager
from itertools import product
from typing import Any


class Approx:
	def __init__(self, expected: float, *, abs: float = 1e-12) -> None:
		self.expected = expected
		self.abs = abs

	def __eq__(self, actual: object) -> bool:
		try:
			return abs(float(actual) - float(self.expected)) <= self.abs
		except (TypeError, ValueError):
			return False


class Raises(AbstractContextManager["Raises"]):
	def __init__(self, expected_exception: type[BaseException], *, match: str | None = None) -> None:
		self.expected_exception = expected_exception
		self.match = match
		self.value: BaseException | None = None

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		traceback: object,
	) -> bool:
		if exc_type is None or exc_value is None:
			raise AssertionError(f"Expected {self.expected_exception.__name__} to be raised")
		if not issubclass(exc_type, self.expected_exception):
			return False
		if self.match is not None and re.search(self.match, str(exc_value)) is None:
			raise AssertionError(f"Exception message {exc_value!r} does not match {self.match!r}")
		self.value = exc_value
		return True


class MonkeyPatch:
	_MISSING = object()

	def __init__(self) -> None:
		self._undo: list[tuple[str, object, object, object]] = []

	def setattr(self, target: object, name: str, value: object, *, raising: bool = True) -> None:
		previous = getattr(target, name, self._MISSING)
		if previous is self._MISSING and raising:
			raise AttributeError(f"{target!r} has no attribute {name!r}")
		self._undo.append(("attr", target, name, previous))
		setattr(target, name, value)

	def setitem(self, mapping: dict[object, object], name: object, value: object) -> None:
		previous = mapping.get(name, self._MISSING)
		self._undo.append(("item", mapping, name, previous))
		mapping[name] = value

	def undo(self) -> None:
		while self._undo:
			kind, target, name, previous = self._undo.pop()
			if kind == "attr":
				if previous is self._MISSING:
					delattr(target, name)
				else:
					setattr(target, name, previous)
				continue
			if previous is self._MISSING:
				del target[name]  # type: ignore[index]
			else:
				target[name] = previous  # type: ignore[index]


class FixtureMarker:
	def __init__(self, *, autouse: bool = False) -> None:
		self.autouse = autouse


class Mark:
	def parametrize(self, argnames: str, argvalues: list[object] | tuple[object, ...]) -> object:
		def _decorate(fn: Any) -> Any:
			marks = list(getattr(fn, "pytestmark", []))
			marks.append(
				type("ParametrizeMark", (), {"name": "parametrize", "args": (argnames, argvalues)})()
			)
			fn.pytestmark = marks
			return fn

		return _decorate


mark = Mark()


def approx(expected: float, *, abs: float = 1e-12) -> Approx:
	return Approx(expected, abs=abs)


def fail(message: str) -> None:
	raise AssertionError(message)


def fixture(*, autouse: bool = False) -> object:
	def _decorate(fn: Any) -> Any:
		fn._bench_fixture_marker = FixtureMarker(autouse=autouse)
		return fn

	return _decorate


def raises(expected_exception: type[BaseException], *, match: str | None = None) -> Raises:
	return Raises(expected_exception, match=match)


def add_pytest_style_tests(
	module_globals: dict[str, Any],
	case_cls: type,
	*,
	excluded: set[str] | None = None,
) -> None:
	excluded = excluded or set()
	for name, fn in sorted(module_globals.items()):
		if name in excluded or not name.startswith("test_") or not callable(fn):
			continue
		setattr(case_cls, name, _build_test_method(module_globals, fn))


def _build_test_method(module_globals: dict[str, Any], fn: Any):
	signature = inspect.signature(fn)
	param_names = list(signature.parameters)
	parametrize_marks = _parametrize_marks(fn)

	def _run_case(param_values: dict[str, Any]) -> None:
		monkeypatch = MonkeyPatch()
		fixture_cache: dict[str, Any] = {}
		try:
			_run_autouse_fixtures(module_globals, monkeypatch, fixture_cache)
			kwargs = _build_kwargs(module_globals, param_names, monkeypatch, fixture_cache, param_values)
			fn(**kwargs)
		finally:
			monkeypatch.undo()

	def _test_method(self) -> None:
		if _is_hypothesis_test(fn):
			fn()
			return

		if not parametrize_marks:
			_run_case({})
			return

		for case_index, param_values in enumerate(_iter_parametrize_cases(parametrize_marks)):
			with self.subTest(case=case_index, params=param_values):
				_run_case(param_values)

	return _test_method


def _run_autouse_fixtures(
	module_globals: dict[str, Any],
	monkeypatch: MonkeyPatch,
	fixture_cache: dict[str, Any],
) -> None:
	for name, fixture in module_globals.items():
		fixture_def = getattr(fixture, "_pytestfixturefunction", None)
		fixture_marker = getattr(fixture, "_fixture_function_marker", None)
		bench_fixture_marker = getattr(fixture, "_bench_fixture_marker", None)
		is_autouse = bool(
			(fixture_def is not None and getattr(fixture_def, "autouse", False))
			or (fixture_marker is not None and getattr(fixture_marker, "autouse", False))
			or (bench_fixture_marker is not None and getattr(bench_fixture_marker, "autouse", False))
		)
		if is_autouse:
			_resolve_fixture(module_globals, name, monkeypatch, fixture_cache)


def _build_kwargs(
	module_globals: dict[str, Any],
	param_names: list[str],
	monkeypatch: MonkeyPatch,
	fixture_cache: dict[str, Any],
	param_values: dict[str, Any],
) -> dict[str, Any]:
	kwargs: dict[str, Any] = {}
	for name in param_names:
		if name in param_values:
			kwargs[name] = param_values[name]
			continue
		if name == "monkeypatch":
			kwargs[name] = monkeypatch
			continue
		kwargs[name] = _resolve_fixture(module_globals, name, monkeypatch, fixture_cache)
	return kwargs


def _resolve_fixture(
	module_globals: dict[str, Any],
	name: str,
	monkeypatch: MonkeyPatch,
	fixture_cache: dict[str, Any],
) -> Any:
	if name in fixture_cache:
		return fixture_cache[name]

	fixture = module_globals.get(name)
	if not callable(fixture):
		raise RuntimeError(f"Unsupported test parameter '{name}'. Add a fixture helper for this name.")

	fixture_fn = getattr(fixture, "__wrapped__", fixture)
	fixture_signature = inspect.signature(fixture_fn)
	kwargs = _build_kwargs(module_globals, list(fixture_signature.parameters), monkeypatch, fixture_cache, {})
	value = fixture_fn(**kwargs)
	fixture_cache[name] = value
	return value


def _parametrize_marks(fn: Any) -> list[Any]:
	marks = getattr(fn, "pytestmark", [])
	return [mark for mark in marks if getattr(mark, "name", "") == "parametrize"]


def _iter_parametrize_cases(marks: list[Any]) -> list[dict[str, Any]]:
	case_dimensions: list[list[dict[str, Any]]] = []
	for mark in marks:
		param_names_raw = mark.args[0]
		param_names = [name.strip() for name in param_names_raw.split(",")]
		dimension: list[dict[str, Any]] = []
		for raw_case in mark.args[1]:
			case_values = raw_case.values if hasattr(raw_case, "values") else raw_case
			if len(param_names) == 1:
				values = (case_values,)
			else:
				values = tuple(case_values)
			dimension.append(dict(zip(param_names, values, strict=False)))
		case_dimensions.append(dimension)

	if not case_dimensions:
		return [{}]

	combined: list[dict[str, Any]] = []
	for combination in product(*case_dimensions):
		merged: dict[str, Any] = {}
		for part in combination:
			merged.update(part)
		combined.append(merged)
	return combined


def _is_hypothesis_test(fn: Any) -> bool:
	return bool(getattr(fn, "is_hypothesis_test", False))
