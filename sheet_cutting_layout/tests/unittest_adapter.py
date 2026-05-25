from __future__ import annotations

import inspect
from itertools import product
from typing import Any

import pytest


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

	def _test_method(self) -> None:
		monkeypatch = pytest.MonkeyPatch()
		fixture_cache: dict[str, Any] = {}
		try:
			_run_autouse_fixtures(module_globals, monkeypatch, fixture_cache)

			if _is_hypothesis_test(fn):
				fn()
				return

			if not parametrize_marks:
				kwargs = _build_kwargs(module_globals, param_names, monkeypatch, fixture_cache, {})
				fn(**kwargs)
				return

			for case_index, param_values in enumerate(_iter_parametrize_cases(parametrize_marks)):
				with self.subTest(case=case_index, params=param_values):
					kwargs = _build_kwargs(
						module_globals,
						param_names,
						monkeypatch,
						fixture_cache,
						param_values,
					)
					fn(**kwargs)
		finally:
			monkeypatch.undo()

	return _test_method


def _run_autouse_fixtures(
	module_globals: dict[str, Any],
	monkeypatch: pytest.MonkeyPatch,
	fixture_cache: dict[str, Any],
) -> None:
	for name, fixture in module_globals.items():
		fixture_def = getattr(fixture, "_pytestfixturefunction", None)
		fixture_marker = getattr(fixture, "_fixture_function_marker", None)
		is_autouse = bool(
			(fixture_def is not None and getattr(fixture_def, "autouse", False))
			or (fixture_marker is not None and getattr(fixture_marker, "autouse", False))
		)
		if is_autouse:
			_resolve_fixture(module_globals, name, monkeypatch, fixture_cache)


def _build_kwargs(
	module_globals: dict[str, Any],
	param_names: list[str],
	monkeypatch: pytest.MonkeyPatch,
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
	monkeypatch: pytest.MonkeyPatch,
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
