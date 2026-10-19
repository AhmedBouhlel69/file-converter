"""Rendered regressions for dialog surfaces and native form controls."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QLabel,
    QRadioButton,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
)

from image_converter.ui.contrast import assert_rendered_label_contrast, assert_theme_contrast
from image_converter.ui.theme import BG, FOCUS_RING, TEXT_PRIMARY, TEXT_SECONDARY, apply_theme
from image_converter.ui.tool_dialogs import (
    CompressDialog,
    ImageCompressDialog,
    MergeDialog,
    OrganizePagesDialog,
    SplitDialog,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    # Windows' offscreen plugin does not discover installed system fonts.
    segoe = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf"
    if segoe.exists():
        QFontDatabase.addApplicationFont(str(segoe))
    return app


@pytest.fixture
def light_os_palette(qapp):
    previous_palette = QPalette(qapp.palette())
    previous_stylesheet = qapp.styleSheet()
    qapp.setStyleSheet("")
    light = QPalette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        light.setColor(role, QColor("#FFFFFF"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        light.setColor(role, QColor("#000000"))
    qapp.setPalette(light)
    yield
    qapp.setPalette(previous_palette)
    qapp.setStyleSheet(previous_stylesheet)


@pytest.mark.parametrize("dialog_class", [MergeDialog, SplitDialog, OrganizePagesDialog, CompressDialog, ImageCompressDialog])
def test_dialog_labels_contrast_on_actual_opaque_surface(qapp, light_os_palette, dialog_class):
    dialog = dialog_class()
    try:
        dialog.show()
        qapp.processEvents()
        root = dialog.grab().toImage().pixelColor(1, 1)
        assert root.alpha() == 255
        assert root.name() == BG.lower()
        assert dialog.palette().color(QPalette.ColorRole.Window).name() == BG.lower()
        assert dialog.findChild(QLabel, "HeaderLabel").palette().color(QPalette.ColorRole.WindowText).name() == TEXT_PRIMARY.lower()
        assert dialog.findChild(QLabel, "MutedLabel").palette().color(QPalette.ColorRole.WindowText).name() == TEXT_SECONDARY.lower()
        ratios = assert_rendered_label_contrast(dialog)
        assert ratios
        assert min(ratios.values()) >= 4.5
        assert_theme_contrast()
    finally:
        dialog.close()


def _indicator_image(control):
    option = QStyleOptionButton()
    option.initFrom(control)
    element = QStyle.SubElement.SE_RadioButtonIndicator if isinstance(control, QRadioButton) else QStyle.SubElement.SE_CheckBoxIndicator
    rect = control.style().subElementRect(element, option, control)
    return _rendered_region(control, rect)


def _rendered_region(widget, logical_rect):
    rendered = widget.grab().toImage()
    device_ratio = rendered.devicePixelRatio()
    physical_rect = QRect(
        round(logical_rect.x() * device_ratio),
        round(logical_rect.y() * device_ratio),
        round(logical_rect.width() * device_ratio),
        round(logical_rect.height() * device_ratio),
    )
    return rendered.copy(physical_rect)


def _count_color(image, target: str, tolerance: int = 15):
    expected = QColor(target)
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if max(abs(image.pixelColor(x, y).red() - expected.red()),
               abs(image.pixelColor(x, y).green() - expected.green()),
               abs(image.pixelColor(x, y).blue() - expected.blue())) <= tolerance
    )


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("state", [Qt.CheckState.Unchecked, Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked])
def test_checkbox_state_has_visible_mark_and_disabled_treatment(qapp, state, enabled):
    surface = QWidget()
    apply_theme(surface)
    layout = QVBoxLayout(surface)
    checkbox = QCheckBox("Remove supported metadata")
    checkbox.setTristate(True)
    checkbox.setCheckState(state)
    checkbox.setEnabled(enabled)
    checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    layout.addWidget(checkbox)
    surface.show()
    qapp.processEvents()
    try:
        indicator = _indicator_image(checkbox)
        marks = _count_color(indicator, "#FFFFFF")
        assert (marks >= 8) if state != Qt.CheckState.Unchecked else (marks == 0)
        if not enabled:
            assert checkbox.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText).name() == "#8092a8"
    finally:
        surface.close()


def test_checkbox_focus_ring_and_radio_dot_render(qapp):
    surface = QWidget()
    apply_theme(surface)
    layout = QVBoxLayout(surface)
    checkbox = QCheckBox("Fit within")
    radio = QRadioButton("Balanced")
    radio.setChecked(True)
    layout.addWidget(checkbox)
    layout.addWidget(radio)
    surface.show()
    surface.activateWindow()
    checkbox.setFocus()
    qapp.processEvents()
    try:
        assert checkbox.hasFocus()
        assert _count_color(_indicator_image(checkbox), FOCUS_RING) >= 8
        assert _count_color(_indicator_image(radio), "#FFFFFF") >= 8
    finally:
        surface.close()


@pytest.mark.parametrize("control_class", [QCheckBox, QRadioButton])
def test_indicator_focus_preserves_geometry_and_label_position(qapp, control_class):
    surface = QWidget()
    apply_theme(surface)
    layout = QVBoxLayout(surface)
    control = control_class("A stable focus target")
    focus_sink = QSpinBox()
    layout.addWidget(control)
    layout.addWidget(focus_sink)
    surface.show()
    surface.activateWindow()
    try:
        indicator_element = QStyle.SubElement.SE_RadioButtonIndicator if isinstance(control, QRadioButton) else QStyle.SubElement.SE_CheckBoxIndicator
        contents_element = QStyle.SubElement.SE_RadioButtonContents if isinstance(control, QRadioButton) else QStyle.SubElement.SE_CheckBoxContents
        geometry = []
        for target in (focus_sink, control):
            target.setFocus()
            qapp.processEvents()
            option = QStyleOptionButton()
            option.initFrom(control)
            indicator = control.style().subElementRect(indicator_element, option, control)
            contents = control.style().subElementRect(contents_element, option, control)
            assert control.rect().contains(indicator)
            geometry.append((indicator, contents.x()))
        assert control.hasFocus()
        assert geometry[0] == geometry[1]
    finally:
        surface.close()


@pytest.mark.parametrize("spinbox_class", [QSpinBox, QDoubleSpinBox])
def test_spinbox_step_buttons_fit_and_have_visible_working_arrows(qapp, spinbox_class):
    surface = QWidget()
    apply_theme(surface)
    layout = QVBoxLayout(surface)
    spinbox = spinbox_class()
    spinbox.setRange(0, 100)
    spinbox.setValue(50)
    layout.addWidget(spinbox)
    surface.show()
    qapp.processEvents()
    try:
        option = QStyleOptionSpinBox()
        spinbox.initStyleOption(option)
        style = spinbox.style()
        up = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxUp, spinbox)
        down = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxDown, spinbox)
        edit = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxEditField, spinbox)
        for button in (up, down):
            assert spinbox.rect().contains(button)
            assert button.width() >= 20
            assert button.height() >= 14
            assert not button.intersects(edit)
            assert _count_color(_rendered_region(spinbox, button), "#DCE8F7", tolerance=25) >= 4
        QTest.mouseClick(spinbox, Qt.MouseButton.LeftButton, pos=up.center())
        assert spinbox.value() == 51
        QTest.mouseClick(spinbox, Qt.MouseButton.LeftButton, pos=down.center())
        assert spinbox.value() == 50
    finally:
        surface.close()


@pytest.mark.parametrize("spinbox_class", [QSpinBox, QDoubleSpinBox])
@pytest.mark.parametrize("value,enabled,up_available,down_available", [(0, True, True, False), (100, True, False, True), (50, False, False, False)])
def test_spinbox_limits_and_disabled_arrows_are_visibly_inactive(qapp, spinbox_class, value, enabled, up_available, down_available):
    surface = QWidget()
    apply_theme(surface)
    layout = QVBoxLayout(surface)
    spinbox = spinbox_class()
    spinbox.setRange(0, 100)
    spinbox.setValue(value)
    spinbox.setEnabled(enabled)
    layout.addWidget(spinbox)
    surface.show()
    qapp.processEvents()
    try:
        option = QStyleOptionSpinBox()
        spinbox.initStyleOption(option)
        for subcontrol, available in ((QStyle.SubControl.SC_SpinBoxUp, up_available), (QStyle.SubControl.SC_SpinBoxDown, down_available)):
            rect = spinbox.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, subcontrol, spinbox)
            region = _rendered_region(spinbox, rect)
            expected = "#DCE8F7" if available else "#8092A8"
            assert _count_color(region, expected, tolerance=25) >= 4
            if not available:
                assert _count_color(region, "#DCE8F7", tolerance=25) == 0
    finally:
        surface.close()


def test_rendered_contrast_rejects_white_on_white_at_200_percent_scaling():
    script = r'''
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from image_converter.ui.contrast import assert_rendered_label_contrast
from image_converter.ui.theme import apply_theme

app = QApplication([])
surface = QWidget()
surface.setObjectName("centralWidget")
surface.resize(400, 300)
apply_theme(surface)
label = QLabel("White on white", surface)
label.setGeometry(100, 120, 160, 40)
label.setStyleSheet("background-color: #FFFFFF; color: #FFFFFF;")
surface.show()
app.processEvents()
assert surface.grab().devicePixelRatio() == 2
try:
    assert_rendered_label_contrast(surface)
except AssertionError as exc:
    assert "1.00:1 on #ffffff" in str(exc), str(exc)
else:
    raise AssertionError("White on white was accepted at 200% scaling")
surface.close()
'''
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="2")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
