"""
ui/animations.py — QPropertyAnimation helpers for the Lowen pill

Provides reusable animation builders so pill.py stays clean.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
)
from PyQt6.QtWidgets import QWidget


def fade_in(
    widget: QWidget,
    duration: int = 200,
    easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
) -> QPropertyAnimation:
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(easing)
    return anim


def fade_out(
    widget: QWidget,
    duration: int = 300,
    easing: QEasingCurve.Type = QEasingCurve.Type.InCubic,
) -> QPropertyAnimation:
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(easing)
    return anim


def slide_down(
    widget: QWidget,
    start_y: int,
    end_y: int,
    duration: int = 250,
) -> QPropertyAnimation:
    """Animate the widget's geometry.y from start_y to end_y."""
    geo = widget.geometry()
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration)
    anim.setStartValue(QRect(geo.x(), start_y, geo.width(), geo.height()))
    anim.setEndValue(QRect(geo.x(), end_y, geo.width(), geo.height()))
    anim.setEasingCurve(QEasingCurve.Type.OutBack)
    return anim


def shake(widget: QWidget, amplitude: int = 8, duration: int = 400) -> QPropertyAnimation:
    """Horizontal shake animation for error state."""
    geo = widget.geometry()
    cx = geo.x()
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration)
    anim.setKeyValueAt(0.0,  QRect(cx,               geo.y(), geo.width(), geo.height()))
    anim.setKeyValueAt(0.15, QRect(cx - amplitude,   geo.y(), geo.width(), geo.height()))
    anim.setKeyValueAt(0.30, QRect(cx + amplitude,   geo.y(), geo.width(), geo.height()))
    anim.setKeyValueAt(0.45, QRect(cx - amplitude//2, geo.y(), geo.width(), geo.height()))
    anim.setKeyValueAt(0.60, QRect(cx + amplitude//2, geo.y(), geo.width(), geo.height()))
    anim.setKeyValueAt(1.0,  QRect(cx,               geo.y(), geo.width(), geo.height()))
    anim.setEasingCurve(QEasingCurve.Type.Linear)
    return anim
