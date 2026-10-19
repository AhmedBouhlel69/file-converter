"""Small WCAG contrast audit for the UI theme tokens."""

from __future__ import annotations

from image_converter.ui.theme import (
    ACCENT,
    BG,
    BORDER,
    FOCUS_RING,
    SURFACE_1,
    SURFACE_2,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4)]

    def linearize(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio for two six-digit hex colors."""
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


TEXT_PAIRS = {
    "primary on app background": (TEXT_PRIMARY, BG),
    "primary on first surface": (TEXT_PRIMARY, SURFACE_1),
    "primary on raised surface": (TEXT_PRIMARY, SURFACE_2),
    "secondary on app background": (TEXT_SECONDARY, BG),
    "secondary on first surface": (TEXT_SECONDARY, SURFACE_1),
    "secondary on raised surface": (TEXT_SECONDARY, SURFACE_2),
    "white on primary action": ("#FFFFFF", ACCENT),
}

NON_TEXT_PAIRS = {
    "focus ring on app background": (FOCUS_RING, BG),
    "focus ring on first surface": (FOCUS_RING, SURFACE_1),
    "boundary on app background": (BORDER, BG),
}


def audit_theme_contrast() -> dict[str, float]:
    """Calculate every contrast pair used by the automated theme audit."""
    return {
        name: contrast_ratio(foreground, background)
        for name, (foreground, background) in {**TEXT_PAIRS, **NON_TEXT_PAIRS}.items()
    }


def assert_theme_contrast() -> dict[str, float]:
    """Fail when text is below 4.5:1 or focus/boundaries are below 3:1."""
    ratios = audit_theme_contrast()
    failures = [
        f"{name}: {ratios[name]:.2f}:1"
        for name in TEXT_PAIRS
        if ratios[name] < 4.5
    ]
    failures.extend(
        f"{name}: {ratios[name]:.2f}:1"
        for name in NON_TEXT_PAIRS
        if ratios[name] < 3.0
    )
    if failures:
        raise AssertionError("Theme contrast audit failed: " + "; ".join(failures))
    return ratios


def assert_rendered_label_contrast(surface, minimum: float = 4.5) -> dict[str, float]:
    """Audit visible labels against their rendered, opaque backing surface.

    Call after showing/polishing the widget. Label perimeters avoid glyph pixels;
    sampling the render also catches a transparent dialog root, which a token
    or palette-only audit would miss.
    """
    from collections import Counter

    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QLabel

    rendered = surface.grab().toImage()
    device_ratio = rendered.devicePixelRatio()
    ratios: dict[str, float] = {}
    failures = []
    for index, label in enumerate(surface.findChildren(QLabel)):
        if not label.text() or not label.isVisibleTo(surface) or label.width() < 2 or label.height() < 2:
            continue
        origin = label.mapTo(surface, QPoint(0, 0))
        # Sample the whole perimeter so a glyph touching one corner cannot
        # masquerade as the background (notably with fallback fonts).
        perimeter = [origin + QPoint(x, y) for x in range(label.width()) for y in (0, label.height() - 1)]
        perimeter.extend(origin + QPoint(x, y) for y in range(1, label.height() - 1) for x in (0, label.width() - 1))
        physical_points = [QPoint(round(point.x() * device_ratio), round(point.y() * device_ratio)) for point in perimeter]
        samples = [rendered.pixelColor(point) for point in physical_points if rendered.rect().contains(point)]
        if not samples:
            continue
        background = QColor.fromRgba(Counter(color.rgba() for color in samples).most_common(1)[0][0])
        name = f"{label.objectName() or 'label'}[{index}] {label.text()[:60]}"
        if background.alpha() != 255:
            failures.append(f"{name}: backing surface is transparent")
            continue
        foreground = label.palette().color(label.foregroundRole())
        ratio = contrast_ratio(foreground.name(), background.name())
        ratios[name] = ratio
        if ratio < minimum:
            failures.append(f"{name}: {ratio:.2f}:1 on {background.name()}")
    if failures:
        raise AssertionError("Rendered label contrast failed: " + "; ".join(failures))
    return ratios


if __name__ == "__main__":
    for pair, ratio in assert_theme_contrast().items():
        print(f"{pair}: {ratio:.2f}:1")
