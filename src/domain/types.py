from dataclasses import dataclass

@dataclass(frozen=True)
class Point:
    x: float = 0.0
    y: float = 0.0

@dataclass(frozen=True)
class Color:
    r: int = 255
    g: int = 255
    b: int = 255
    a: int = 255

@dataclass(frozen=True)
class Rect:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
