"""
Pressure-coefficient map visualization over the building's 5 faces.

Layout ("exploded view": roof center, wall1 left, wall2 top, wall3 right, wall4 bottom) follows
Figure 9 of the WERFL Data Description PDF (resources/WERFL_Data_Description.pdf, p.27).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Rectangle, FancyArrow
from scipy.interpolate import griddata

from pywerfl import qc, reference_data, summarizer
from pywerfl.loader import Run


def _face_extents() -> dict[str, tuple[float, float]]:
    """{surface: (width_ft, height_ft)}, from the bundled tap-location reference table."""
    locs = reference_data.load_tap_locations()
    return {surf: (g.x_ft.max(), g.y_ft.max()) for surf, g in locs.groupby("surface")}


# (x_ft, y_ft, true_w, true_h) -> (frac_x, frac_y) in [0,1]x[0,1], per face
_FACE_TRANSFORMS = {
    "roof": lambda x, y, w, h: (x / w, y / h),
    "wall1": lambda x, y, w, h: (y / h, x / w),         # transpose: length -> vertical, height -> horizontal
    "wall3": lambda x, y, w, h: (1 - y / h, x / w),     # transpose + flip (roofline faces left, toward roof)
    "wall2": lambda x, y, w, h: (1 - x / w, y / h),     # flip (wall1-adjacent end -> left, toward wall1)
    "wall4": lambda x, y, w, h: (x / w, y / h),
}


def _face_layout(wall_scale: float, gap: float) -> dict[str, tuple[float, float, float, float]]:
    """{surface: (x0, y0, width, height)} placement rectangles for the composite plot."""
    extents = _face_extents()
    roof_w, roof_h = extents["roof"]
    layout = {"roof": (-roof_w / 2, -roof_h / 2, roof_w, roof_h)}

    for surf, side in (("wall2", "top"), ("wall4", "bottom")):
        w, h = (v * wall_scale for v in extents[surf])
        y = roof_h / 2 + gap if side == "top" else -roof_h / 2 - gap - h
        layout[surf] = (-w / 2, y, w, h)

    thickness = extents["wall1"][1] * wall_scale  # true wall height, shrunk - the "sticking out" dimension
    layout["wall1"] = (-roof_w / 2 - gap - thickness, -roof_h / 2, thickness, roof_h)
    layout["wall3"] = (roof_w / 2 + gap, -roof_h / 2, thickness, roof_h)
    return layout


def _interpolate(points: np.ndarray, values: np.ndarray, x0: float, y0: float, w: float, h: float, resolution: int):
    """Cubic interpolation of scattered (drawn-space) points -> value onto a (resolution x resolution)
    grid spanning [x0,x0+w] x [y0,y0+h], with nearest-neighbor fill outside the tap convex hull."""
    xi, yi = np.linspace(x0, x0 + w, resolution), np.linspace(y0, y0 + h, resolution)
    grid_x, grid_y = np.meshgrid(xi, yi)
    z = griddata(points, values, (grid_x, grid_y), method="cubic")
    missing = np.isnan(z)
    if missing.any() and len(points) >= 1:
        z[missing] = griddata(points, values, (grid_x, grid_y), method="nearest")[missing]
    return z


def _draw_face(ax, surf: str, tap_coords: pd.DataFrame, values: pd.Series, rect, true_size, cmap, norm, interpolate_map: bool, show_points: bool, resolution: int):
    x0, y0, w, h = rect
    true_w, true_h = true_size
    v = values.reindex(tap_coords.index).to_numpy(dtype=float)
    valid = ~np.isnan(v)

    frac_x, frac_y = _FACE_TRANSFORMS[surf](tap_coords["x_ft"].to_numpy(), tap_coords["y_ft"].to_numpy(), true_w, true_h)
    px, py = x0 + frac_x * w, y0 + frac_y * h

    if interpolate_map and valid.sum() >= 3:
        z = _interpolate(np.column_stack([px[valid], py[valid]]), v[valid], x0, y0, w, h, resolution)
        ax.imshow(z, extent=(x0, x0 + w, y0, y0 + h), origin="lower", cmap=cmap, norm=norm, aspect="auto", zorder=1)

    if show_points or not interpolate_map:
        ax.scatter(px, py, c=v, cmap=cmap, norm=norm, edgecolors="k", linewidths=0.5, s=25, zorder=2)

    ax.add_patch(Rectangle((x0, y0), w, h, fill=False, edgecolor="k", linewidth=1, zorder=3))


def _nearest_roof_corner(layout: dict, angle_deg: float) -> tuple[float, float]:
    x0, y0, w, h = layout["roof"]
    cx, cy = x0 + w / 2, y0 + h / 2
    corners = [(x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)]

    def _angular_gap(corner):
        corner_angle = np.degrees(np.arctan2(corner[1] - cy, corner[0] - cx)) % 360
        diff = abs(corner_angle - angle_deg) % 360
        return min(diff, 360 - diff)

    return min(corners, key=_angular_gap)


def _draw_orientation(ax, metadata: dict, layout: dict, arrow_scale: float) -> None:
    aoa = metadata.get("angle_of_attack_deg")
    speed = metadata.get("mean_wind_speed_ms")
    if aoa is not None and speed is not None:
        source_angle = np.radians((180 - aoa) % 360)
        corner_x, corner_y = _nearest_roof_corner(layout, np.degrees(source_angle))
        length = arrow_scale * layout["roof"][2]
        dx, dy = length * np.cos(source_angle), length * np.sin(source_angle)
        start_x, start_y = corner_x + dx, corner_y + dy
        ax.add_patch(FancyArrow(start_x, start_y, -dx, -dy, width=layout["roof"][2] * 0.01,
                                 head_width=layout["roof"][2] * 0.05, length_includes_head=True,
                                 color="black", zorder=5))
        ax.annotate(f"{speed:.1f} m/s", (start_x, start_y), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, zorder=5)

    bp = metadata.get("building_position_deg")
    if bp is not None:
        corner_x = layout["wall3"][0] + layout["wall3"][2] + layout["roof"][2] * 0.08
        corner_y = layout["wall2"][1] + layout["wall2"][3] + layout["roof"][2] * 0.08
        north_angle = np.radians((bp + 180) % 360)
        r = layout["roof"][2] * 0.06
        ax.annotate("N", (corner_x, corner_y), ha="center", va="center", fontsize=9, fontweight="bold", zorder=5)
        ax.add_patch(FancyArrow(corner_x - r * np.cos(north_angle), corner_y - r * np.sin(north_angle),
                                 2 * r * np.cos(north_angle), 2 * r * np.sin(north_angle),
                                 width=r * 0.06, head_width=r * 0.3, length_includes_head=True,
                                 color="dimgray", zorder=5))


def _resolve_values(run: Run, stat: str | None, time: float | None, values: pd.Series | None) -> pd.Series:
    if values is not None:
        return values
    if time is not None:
        idx = run.cp.index[np.argmin(np.abs(run.cp.index - time))]
        return run.cp.loc[idx]
    return summarizer.summarize_run(run).cp[stat if stat is not None else "mean"]


def _fit_axes_to_layout(ax, layout: dict) -> None:
    xs = [x0 for x0, y0, w, h in layout.values()] + [x0 + w for x0, y0, w, h in layout.values()]
    ys = [y0 for x0, y0, w, h in layout.values()] + [y0 + h for x0, y0, w, h in layout.values()]
    margin = 0.1 * max(max(xs) - min(xs), max(ys) - min(ys))
    ax.set_xlim(min(xs) - margin, max(xs) + margin)
    ax.set_ylim(min(ys) - margin, max(ys) + margin)
    ax.set_aspect("equal")
    ax.axis("off")


def _setup_axes(ax, layout, values):
    vmax = np.nanmax(np.abs(values.to_numpy(dtype=float)))
    vmax = vmax if vmax > 0 else 1.0
    norm = TwoSlopeNorm(vcenter=0, vmin=-vmax, vmax=vmax)
    _fit_axes_to_layout(ax, layout)
    return norm


def plot_pressure_map(
    run: Run,
    stat: str = "mean",
    time: float | None = None,
    values: pd.Series | None = None,
    show_points: bool = False,
    interpolate: bool = True,
    wall_scale: float = 0.5,
    gap: float = 3.0,
    resolution: int = 60,
    arrow_scale: float = 0.4,
    cmap: str = "RdBu_r",
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """
    Cp map over the building's 5 faces, from a Run object.
    """
    v = _resolve_values(run, stat, time, values)
    locs = reference_data.load_tap_locations().set_index("tap_id")
    extents = _face_extents()
    layout = _face_layout(wall_scale, gap)

    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 9))
    norm = _setup_axes(ax, layout, v)

    for surf, rect in layout.items():
        _draw_face(ax, surf, locs[locs.surface == surf], v, rect, extents[surf], cmap, norm, interpolate, show_points, resolution)

    _draw_orientation(ax, run.metadata, layout, arrow_scale)

    if values is not None:
        label = "custom values"
    elif time is not None:
        label = f"t={time:.2f}s"
    else:
        label = stat

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    (fig or ax.figure).colorbar(sm, ax=ax, shrink=0.7, label="Cp")
    ax.set_title(f"Run {run.run_id} - {label}")
    return fig or ax.figure


def animate_pressure_map(
    run: Run,
    max_frames: int = 200,
    stride: int | None = None,
    show_points: bool = False,
    interpolate: bool = True,
    wall_scale: float = 0.5,
    gap: float = 3.0,
    resolution: int = 40,
    arrow_scale: float = 0.4,
    cmap: str = "RdBu_r",
    interval_ms: int = 50,
) -> FuncAnimation:
    """Animated Cp map over run.cp's full time series. Returns a matplotlib FuncAnimation."""
    cp = run.cp
    stride = stride if stride is not None else max(1, len(cp) // max_frames)
    frame_indices = cp.index[::stride]

    locs = reference_data.load_tap_locations().set_index("tap_id")
    extents = _face_extents()
    layout = _face_layout(wall_scale, gap)

    fig, ax = plt.subplots(figsize=(9, 9))
    norm = _setup_axes(ax, layout, cp.stack())

    def render(i):
        ax.clear()
        _setup_axes(ax, layout, cp.stack())
        v = cp.loc[frame_indices[i]]
        for surf, rect in layout.items():
            _draw_face(ax, surf, locs[locs.surface == surf], v, rect, extents[surf], cmap, norm, interpolate, show_points, resolution)
        _draw_orientation(ax, run.metadata, layout, arrow_scale)
        ax.set_title(f"Run {run.run_id} - t={frame_indices[i]:.2f}s")

    return FuncAnimation(fig, render, frames=len(frame_indices), interval=interval_ms)


def plot_tap_locations(
    wall_scale: float = 0.5,
    gap: float = 3.0,
    fontsize: float = 5,
    alternate_labels: bool = True,
    ax: plt.Axes | None = None,
) -> plt.Figure:
    """
    Reference tap locations (pywerfl.reference_data) labeled with tap IDs.
    TODO: allow passing a run to see which taps are instrumented?

    alternate_labels: alternate each face's labels above/below their point by column, so labels
    stagger horizontally without adjacent rows in the same column colliding; False puts every
    label above its point.
    """
    locs = reference_data.load_tap_locations().set_index("tap_id")
    extents = _face_extents()
    layout = _face_layout(wall_scale, gap)

    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 9))
    _fit_axes_to_layout(ax, layout)

    for surf, rect in layout.items():
        x0, y0, w, h = rect
        true_w, true_h = extents[surf]
        face_taps = locs[locs.surface == surf]
        frac_x, frac_y = _FACE_TRANSFORMS[surf](face_taps["x_ft"].to_numpy(), face_taps["y_ft"].to_numpy(), true_w, true_h)
        px, py = x0 + frac_x * w, y0 + frac_y * h

        ax.scatter(px, py, s=10, c="black", zorder=2)
        # group by drawn (not raw) horizontal position - wall1/wall3 are transposed, so x_ft maps
        # to the drawn vertical axis there, not horizontal
        frac_x_rounded = np.round(frac_x, 6)
        col_index = {v: i for i, v in enumerate(sorted(set(frac_x_rounded)))}
        col_flip = np.array([col_index[v] % 2 == 1 for v in frac_x_rounded])
        for tap_id, x, y, flip in zip(face_taps.index, px, py, col_flip):
            below = alternate_labels and flip
            ax.annotate(tap_id, (x, y), fontsize=fontsize, ha="center", va="top" if below else "bottom",
                        xytext=(0, -4 if below else 4), textcoords="offset points", zorder=3)
        ax.add_patch(Rectangle((x0, y0), w, h, fill=False, edgecolor="k", linewidth=1, zorder=1))

    ax.set_title("Tap locations")
    return fig or ax.figure


def plot_tap_diagnostic(run: Run, tap_id: str, bins: int = 50) -> plt.Figure:
    """
    Time series + histogram for one Cp tap, with diagnostic stats (mean/std/median/mad/min/max/
    unique-value count) in the title, for inspecting a suspicious tap found by
    pywerfl.qc.find_suspicious_taps. Pass a Run loaded with exclude_taps=False to see the true
    raw signal even if this tap is already on the exclusion list.
    """
    series = run.cp[tap_id]
    d = qc.tap_diagnostics(series)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    ax1.plot(series.index, series, linewidth=0.5)
    ax1.set_xlabel("elapsed_seconds")
    ax1.set_ylabel("Cp")
    ax1.set_title("Time series")

    ax2.hist(series.dropna(), bins=bins)
    ax2.set_xlabel("Cp")
    ax2.set_ylabel("count")
    ax2.set_title("Histogram")

    stats_line = (
        f"mean={d['mean']:.3f}  std={d['std']:.3f}  median={d['median']:.3f}  mad={d['mad']:.3f}  "
        f"min={d['min']:.3f}  max={d['max']:.3f}  unique={d['n_unique']} ({d['unique_frac']:.1%})"
    )
    fig.suptitle(f"Run {run.run_id} - tap {tap_id}\n{stats_line}")
    fig.tight_layout()
    return fig
