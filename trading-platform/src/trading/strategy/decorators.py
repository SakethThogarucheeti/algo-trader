from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading.strategy.base import Strategy


def strategy(alias: str):
    """
    Class decorator that registers a Strategy subclass under *alias*.

    Syntactic sugar over setting ``alias`` as a class attribute — both
    approaches produce identical registry entries.

    Usage
    -----
        @strategy("my_strategy")
        class MyStrategy(Strategy):
            def on_candle(self, symbol, instrument_type, df):
                ...

    The decorator is optional. Directly assigning ``alias = "my_strategy"``
    inside the class body is equivalent and slightly more explicit.

    Raises
    ------
    TypeError
        If the decorated class is not a Strategy subclass.
    ValueError
        If *alias* is already claimed by a different class.
    """
    if not isinstance(alias, str) or not alias:
        raise TypeError(f"@strategy alias must be a non-empty string, got {alias!r}")

    def decorator(cls: type[Strategy]) -> type[Strategy]:
        from trading.strategy.base import Strategy as _Strategy

        if not (isinstance(cls, type) and issubclass(cls, _Strategy)):
            raise TypeError(
                f"@strategy can only decorate Strategy subclasses, got {cls!r}"
            )
        # Inject the alias attribute, which triggers __init_subclass__ registration.
        # If the class was already defined without an alias, we need to register it now.
        if "alias" not in cls.__dict__:
            cls.alias = alias  # type: ignore[attr-defined]
            # __init_subclass__ already fired at class-creation time without an alias,
            # so we must register manually here.
            from trading.strategy.base import _REGISTRY, _log
            if alias in _REGISTRY and _REGISTRY[alias] is not cls:
                existing = _REGISTRY[alias]
                raise ValueError(
                    f"Duplicate strategy alias {alias!r}: already registered by "
                    f"{existing.__qualname__}, cannot also register {cls.__qualname__}."
                )
            _REGISTRY[alias] = cls
            _log.debug("Strategy registered via decorator: %r → %s", alias, cls.__qualname__)
        elif cls.__dict__["alias"] != alias:
            raise ValueError(
                f"@strategy({alias!r}) conflicts with class-level alias={cls.__dict__['alias']!r} "
                f"on {cls.__qualname__}. Use one or the other, not both."
            )
        return cls

    return decorator
