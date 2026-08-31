"""
Circular (angular) statistics module.

skew/kurt formulas: Fisher, "Statistical Analysis of Circular Data" (1993).
"""

from __future__ import annotations

import numpy as np


def trigonometric_moment(directions, magnitudes=1.0, order: int = 1, degrees: bool = True) -> tuple[float, float]:
    """
    p-th trigonometric moment (R_p, mu_p) of `order`*directions, optionally magnitude-weighted.
    magnitudes=1.0 (default): standard unit-vector circular moment. Real per-sample magnitudes
    at order=1: true vector average. NaN-safe.
    """
    rad = np.deg2rad(directions) if degrees else np.asarray(directions, dtype=float)
    theta = order * np.asarray(rad, dtype=float)
    x_terms, y_terms = magnitudes * np.cos(theta), magnitudes * np.sin(theta)
    valid = ~(np.isnan(x_terms) | np.isnan(y_terms))
    if not np.any(valid):
        return np.nan, np.nan
    x, y = x_terms[valid].mean(), y_terms[valid].mean()
    r = np.hypot(x, y)
    mu = np.arctan2(y, x)
    return r, (np.rad2deg(mu) % 360 if degrees else mu % (2 * np.pi))


def vector_mean(magnitudes, directions, degrees: bool = True) -> tuple[float, float]:
    """True (speed-weighted) vector average: (mean magnitude, mean direction)."""
    return trigonometric_moment(directions, magnitudes=magnitudes, order=1, degrees=degrees)


def circular_mean(directions, degrees: bool = True) -> float:
    """Unit-vector circular mean (magnitude ignored)."""
    return trigonometric_moment(directions, order=1, degrees=degrees)[1]


def angular_distance(theta, phi, degrees: bool = True):
    """Minimum angular distance between theta and phi."""
    mod = 360 if degrees else 2 * np.pi
    d0 = (np.asarray(theta, dtype=float) - phi) % mod
    return np.minimum(mod - d0, d0)


def circular_std(directions, degrees: bool = True) -> float:
    """Yamartino-style circular std: RMS angular deviation from the unit-vector circular mean."""
    mean_direction = circular_mean(directions, degrees=degrees)
    if np.isnan(mean_direction):
        return np.nan
    deviations = angular_distance(directions, mean_direction, degrees=degrees)
    variance = np.nanmean(deviations**2) - np.nanmean(deviations) ** 2
    return variance**0.5


def circular_skew(directions, degrees: bool = True) -> float:
    """Circular skewness: R_2 sin(mu_2 - 2 mu_1) / (1 - R_1)^1.5, referenced to the unit-vector mean."""
    r1, mu1 = trigonometric_moment(directions, order=1, degrees=degrees)
    r2, mu2 = trigonometric_moment(directions, order=2, degrees=degrees)
    if np.isnan(r1) or np.isnan(r2):
        return np.nan
    diff = np.deg2rad(mu2 - 2 * mu1) if degrees else (mu2 - 2 * mu1)
    return (r2 * np.sin(diff)) / (1 - r1) ** 1.5


def circular_kurt(directions, degrees: bool = True) -> float:
    """Circular kurtosis: (R_2 cos(mu_2 - 2 mu_1) - R_1^4) / (1 - R_1)^2, referenced to the unit-vector mean."""
    r1, mu1 = trigonometric_moment(directions, order=1, degrees=degrees)
    r2, mu2 = trigonometric_moment(directions, order=2, degrees=degrees)
    if np.isnan(r1) or np.isnan(r2):
        return np.nan
    diff = np.deg2rad(mu2 - 2 * mu1) if degrees else (mu2 - 2 * mu1)
    return (r2 * np.cos(diff) - r1**4) / (1 - r1) ** 2
