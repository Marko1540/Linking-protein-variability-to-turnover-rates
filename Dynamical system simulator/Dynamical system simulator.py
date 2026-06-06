from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem, QSplitter,
    QColorDialog, QSpinBox, QCheckBox, QTabWidget,
    QToolButton, QMenu, QTabBar, QSizePolicy,
    QDoubleSpinBox, QScrollArea, QGroupBox, QFrame, QComboBox, QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QAction
from PyQt6.QtCore import Qt, QPointF, QTimer, QRect

import sys, math, time, json, random
from collections import deque
import ast
import numpy as np


# --------------------- Time graph overlays ---------------------

class TimeGraphOverlay(QWidget):
    """Small overlay plot for one variable and its derivative.

    Features:
      - Interactive legend to hide/show curves.
      - Support for multiple systems (each system has its own color).
      - Support for custom expression traces.
      - Dual-axis ticks with different colors for main/derivative.
    """

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind  # 'x' or 'y'
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self.window_seconds = 8.0
        self._bg_alpha = 185
        self._grid_alpha = 40

        # Traces per system: system_id -> {'main_samples': deque, 'deriv_samples': deque, 'color': QColor, 'show_main': bool, 'show_deriv': bool, 'label': str}
        self.system_traces = {}

        # Custom traces (for custom functions)
        self.custom_traces = []
        # Items: {'expr': str, 'fn': callable, 'samples': deque, 'color': QColor, 'visible': bool, 'label': str}

        # Legend interaction
        self.legend_rects = {}

        self.dark_mode = True

        # UI for adding custom functions
        self.btn_add = QToolButton(self)
        self.btn_add.setText('+')
        self.btn_add.setToolTip("Add custom function trace")
        self.btn_add.setFixedSize(20, 20)
        self.btn_add.clicked.connect(self._on_add_click)

        self.txt_input = QLineEdit(self)
        self.txt_input.setPlaceholderText("expr (e.g. sin(t))")
        self.txt_input.setVisible(False)
        self.txt_input.returnPressed.connect(self._on_input_commit)
        self.txt_input.editingFinished.connect(self._on_input_hide)

        self.current_t = 0.0  # Track current simulation time

        # When True, μ/σ annotations are computed from all samples since t=0
        # rather than only the currently displayed window.
        self.stats_use_full_history = False

    def resizeEvent(self, ev):
        w, h = self.width(), self.height()
        self.btn_add.move(w - 24, 4)
        self.txt_input.setGeometry(40, 4, w - 70, 20)
        super().resizeEvent(ev)

    def _on_add_click(self):
        self.txt_input.setVisible(True)
        self.txt_input.setFocus()

    def _on_input_hide(self):
        QTimer.singleShot(100, lambda: self.txt_input.setVisible(False) if not self.txt_input.hasFocus() else None)

    def _on_input_commit(self):
        txt = self.txt_input.text().strip()
        if txt and self.parent():
            try:
                env = getattr(self.parent(), 'model_env', {})
                fn = compile_expr(txt, extra_names=env)

                col = QColor(random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))

                trace = {
                    'expr': txt,
                    'fn': fn,
                    'samples': deque(maxlen=4000),
                    'color': col,
                    'visible': True,
                    'label': txt
                }
                self.custom_traces.append(trace)
                self.update()
            except Exception as e:
                print(f"Error compiling custom trace: {e}")

        self.txt_input.clear()
        self.txt_input.setVisible(False)

    def add_system(self, system_id: str, color: QColor, label: str):
        if system_id not in self.system_traces:
            self.system_traces[system_id] = {
                'main_samples': deque(maxlen=10000),
                'deriv_samples': deque(maxlen=10000),
                'color': QColor(color),
                'show_main': True,
                'show_deriv': True,
                'label': label
            }

    def remove_system(self, system_id: str):
        if system_id in self.system_traces:
            del self.system_traces[system_id]

    def update_system_color(self, system_id: str, color: QColor):
        if system_id in self.system_traces:
            self.system_traces[system_id]['color'] = QColor(color)

    def update_system_label(self, system_id: str, label: str):
        if system_id in self.system_traces:
            self.system_traces[system_id]['label'] = label

    def recompile_custom_traces(self):
        """Recompile all custom traces with the current model environment.

        This is needed when parameters or step functions are updated,
        so that the traces use the new function definitions.
        """
        if not self.parent():
            return

        env = getattr(self.parent(), 'model_env', {})
        for trace in self.custom_traces:
            try:
                # Recompile the function with the updated environment
                trace['fn'] = compile_expr(trace['expr'], extra_names=env)
                # Clear old samples since they were computed with the old function
                trace['samples'].clear()
            except Exception as e:
                print(f"Error recompiling trace '{trace['expr']}': {e}")
    '''
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            pos = ev.pos()
            for key, rect in self.legend_rects.items():
                if rect.contains(pos):
                    if isinstance(key, tuple):
                        sys_id, trace_type = key
                        if sys_id in self.system_traces:
                            if trace_type == 'main':
                                self.system_traces[sys_id]['show_main'] = not self.system_traces[sys_id]['show_main']
                            else:
                                self.system_traces[sys_id]['show_deriv'] = not self.system_traces[sys_id]['show_deriv']
                    elif isinstance(key, int) and 0 <= key < len(self.custom_traces):
                        self.custom_traces[key]['visible'] = not self.custom_traces[key]['visible']
                    self.update()
                    return
        ev.ignore()
    '''
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            pos = ev.pos()
            canvas = self.parent()
            for key, rect in self.legend_rects.items():
                if rect.contains(pos):
                    if isinstance(key, tuple) and len(key) == 2:
                        system_uid, trace_type = key
                        # Toggle all particles of this system
                        for p in canvas.particles:
                            if p.system_id == system_uid and p.uid in self.system_traces:
                                tr = self.system_traces[p.uid]
                                if trace_type == 'main':
                                    tr['show_main'] = not tr['show_main']
                                else:
                                    tr['show_deriv'] = not tr['show_deriv']
                    elif isinstance(key, int):
                        # Custom trace toggle
                        self.custom_traces[key]['visible'] = not self.custom_traces[key]['visible']
                    self.update()
                    return
        ev.ignore()

    def set_dark_mode(self, v: bool):
        self.dark_mode = bool(v)
        self.update()

    @staticmethod
    def _nice_step(span: float) -> float:
        span = abs(float(span))
        if not math.isfinite(span) or span <= 1e-12:
            return 1.0
        target = span / 4.0
        exp10 = math.floor(math.log10(target))
        base = 10 ** exp10
        for m in (1.0, 2.0, 5.0, 10.0):
            step = m * base
            if step >= target:
                return float(step)
        return float(10.0 * base)

    @staticmethod
    def _fmt(v: float) -> str:
        if not math.isfinite(v):
            return ''
        if abs(v) < 1e-12:
            v = 0.0
        av = abs(v)
        if av >= 1000 or (av > 0 and av < 0.01):
            return f'{v:.2e}'
        if av >= 100:
            return f'{v:.0f}'
        if av >= 10:
            return f'{v:.1f}'.rstrip('0').rstrip('.')
        return f'{v:.2f}'.rstrip('0').rstrip('.')

    def clear(self):
        for tr in self.system_traces.values():
            tr['main_samples'].clear()
            tr['deriv_samples'].clear()
        for tr in self.custom_traces:
            tr['samples'].clear()
        self.update()

    def push_sample(self, system_id: str, t: float, v: float):
        if system_id not in self.system_traces:
            return
        if not math.isfinite(t) or not math.isfinite(v):
            return
        tr = self.system_traces[system_id]
        s = tr['main_samples']

        # Handle time discontinuity (reset)
        if s and t < s[-1][0] - 1e-12:
            s.clear()
            tr['deriv_samples'].clear()

        s.append((float(t), float(v)))

        # Compute derivative from this trace's own data
        if len(s) >= 2:
            t0, v0 = s[-2]
            t1, v1 = s[-1]
            dt = t1 - t0
            if dt > 1e-12:
                deriv = (v1 - v0) / dt
                tr['deriv_samples'].append((t1, deriv))

    def push_custom_sample(self, idx: int, t: float, v: float):
        if 0 <= idx < len(self.custom_traces):
            s = self.custom_traces[idx]['samples']
            if s and t < s[-1][0] - 1e-12:
                return
            s.append((float(t), float(v)))

    def update_custom_traces(self, x: float, y: float, t: float, state_provider=None):
        """Evaluate and record points for all custom traces."""
        for tr in self.custom_traces:
            try:
                val = float(tr['fn'](x, y, t, state_provider=state_provider))
            except Exception:
                val = 0.0

            s = tr['samples']
            if s and t < s[-1][0] - 1e-12:
                continue
            s.append((float(t), val))

    def _windowed_samples(self, samples):
        if not samples:
            return []
        t_min = self.current_t - self.window_seconds
        return [s for s in samples if s[0] >= t_min]

    '''
    def _windowed_custom(self, trace):
        if not trace['samples']:
            return []
        # Find latest time from any source
        t_now = trace['samples'][-1][0]
        for tr in self.system_traces.values():
            if tr['main_samples']:
                t_now = max(t_now, tr['main_samples'][-1][0])
        t0 = t_now - float(self.window_seconds)
        return [s for s in trace['samples'] if s[0] >= t0]
        '''

    def _windowed_custom(self, trace):
        if not trace['samples']:
            return []
        t_min = self.current_t - self.window_seconds
        return [s for s in trace['samples'] if s[0] >= t_min]

    @staticmethod
    def _finite_diff(samples):
        if len(samples) < 2:
            return []
        out = []
        for i in range(1, len(samples)):
            t0, v0 = samples[i - 1]
            t1, v1 = samples[i]
            dt = t1 - t0
            if dt <= 1e-12:
                continue
            out.append((t1, (v1 - v0) / dt))
        return out

    def _nice_ylim(self, vmin: float, vmax: float):
        if not math.isfinite(vmin) or not math.isfinite(vmax):
            return -1.0, 1.0
        if abs(vmax - vmin) < 1e-9:
            mid = 0.5 * (vmax + vmin)
            span = 1.0 if abs(mid) < 1e-6 else abs(mid) * 0.5
            return mid - span, mid + span
        pad = 0.08 * (vmax - vmin)
        return vmin - pad, vmax + pad

    def paintEvent(self, ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.dark_mode:
            bg = QColor(8, 10, 14, self._bg_alpha)
            fg = QColor(220, 230, 245)
            grid = QColor(255, 255, 255, self._grid_alpha)
        else:
            bg = QColor(255, 255, 255, self._bg_alpha)
            fg = QColor(20, 20, 20)
            grid = QColor(0, 0, 0, self._grid_alpha)

        rect = self.rect()
        painter.fillRect(rect, bg)

        pad_l, pad_r, pad_t, pad_b = 45, 45, 30, 30
        x0 = pad_l
        y0 = pad_t
        x1 = rect.width() - pad_r
        y1 = rect.height() - pad_b
        if x1 <= x0 + 10 or y1 <= y0 + 10:
            return

        painter.fillRect(QRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0)), bg)

        pen = QPen(fg)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))

        # Collect traces into two groups: main (lighter) and deriv (darker)
        group_main = []  # Main variable traces + custom traces
        group_deriv = []  # Derivative traces

        for sys_id, tr in self.system_traces.items():
            main_samples = self._windowed_samples(tr['main_samples'])
            deriv_samples = self._finite_diff(main_samples)

            base_color = tr['color']
            # Lighter color for main
            main_color = QColor(base_color)
            main_color.setAlphaF(1.0)
            # Darker color for derivative
            deriv_color = QColor(int(base_color.red() * 0.7), int(base_color.green() * 0.7), int(base_color.blue() * 0.7))
            deriv_color.setAlphaF(0.8)

            if tr['show_main'] and len(main_samples) >= 2:
                group_main.append({'pts': main_samples, 'color': main_color, 'width': 2, 'sys_id': sys_id, 'type': 'main'})
            if tr['show_deriv'] and len(deriv_samples) >= 2:
                group_deriv.append({'pts': deriv_samples, 'color': deriv_color, 'width': 1, 'sys_id': sys_id, 'type': 'deriv'})

        # Add custom traces to main group
        for tr in self.custom_traces:
            if tr['visible']:
                pts = self._windowed_custom(tr)
                if len(pts) >= 2:
                    group_main.append({'pts': pts, 'color': tr['color'], 'width': 2, 'type': 'custom'})

        all_traces = group_main + group_deriv

        if not all_traces:
            self._draw_legend(painter, fg, x0, y0)
            return

        # Determine time range from all traces
        all_pts = []
        for item in all_traces:
            all_pts.extend(item['pts'])

        t_min, t_max = 0.0, 1.0
        if all_pts:
            t_vals = [p[0] for p in all_pts]
            t_min, t_max = min(t_vals), max(t_vals)
        if t_max - t_min < 1e-9:
            t_min -= 0.5
            t_max += 0.5

        # Determine value ranges for each group
        def get_v_range(group):
            vals = []
            for item in group:
                vals.extend([p[1] for p in item['pts']])
            if not vals:
                return -1.0, 1.0, False
            vmin, vmax = self._nice_ylim(min(vals), max(vals))
            return vmin, vmax, True

        min_main, max_main, has_main = get_v_range(group_main)
        min_deriv, max_deriv, has_deriv = get_v_range(group_deriv)

        def map_lin(val, low, high, out_low, out_high):
            if abs(high - low) < 1e-12:
                norm = 0.5
            else:
                norm = (val - low) / (high - low)
            return out_low + norm * (out_high - out_low)

        painter.setFont(QFont('Courier', 8))

        # Draw grid
        grid_pen = QPen(grid)
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)

        if self.kind == 'x':
            for k in range(1, 5):
                sy = y1 - (y1 - y0) * (k / 5.0)
                painter.drawLine(QPointF(x0, sy), QPointF(x1, sy))
            for k in range(1, 5):
                sx = x0 + (x1 - x0) * (k / 5.0)
                painter.drawLine(QPointF(sx, y0), QPointF(sx, y1))
        else:
            for k in range(1, 5):
                sx = x0 + (x1 - x0) * (k / 5.0)
                painter.drawLine(QPointF(sx, y0), QPointF(sx, y1))
            for k in range(1, 5):
                sy = y0 + (y1 - y0) * (k / 5.0)
                painter.drawLine(QPointF(x0, sy), QPointF(x1, sy))

        # Draw traces
        def draw_traces(group, vmin, vmax):
            for item in group:
                pts = item['pts']
                path_pts = []
                for (t, v) in pts:
                    if self.kind == 'x':
                        sy = map_lin(t, t_min, t_max, y1, y0)
                        sx = map_lin(v, vmin, vmax, x0, x1)
                    else:
                        sx = map_lin(t, t_min, t_max, x0, x1)
                        sy = map_lin(v, vmin, vmax, y1, y0)
                    path_pts.append(QPointF(sx, sy))

                pen = QPen(item['color'])
                pen.setWidth(item['width'])
                painter.setPen(pen)
                for i in range(len(path_pts) - 1):
                    painter.drawLine(path_pts[i], path_pts[i + 1])

        if has_main:
            draw_traces(group_main, min_main, max_main)
        if has_deriv:
            draw_traces(group_deriv, min_deriv, max_deriv)

        # Draw ticks - Time axis
        painter.setPen(fg)
        t_step = self._nice_step(t_max - t_min)
        t_start = math.floor(t_min / t_step) * t_step
        curr_t = t_start
        while curr_t <= t_max + 1e-9:
            txt = self._fmt(curr_t)
            if self.kind == 'x':
                sy = map_lin(curr_t, t_min, t_max, y1, y0)
                if y0 <= sy <= y1:
                    painter.drawText(2, int(sy) + 4, txt)
            else:
                sx = map_lin(curr_t, t_min, t_max, x0, x1)
                if x0 <= sx <= x1:
                    painter.drawText(int(sx) - 10, int(y1) + 15, txt)
            curr_t += t_step

        # Draw value axis ticks with dual scale (lighter for main, darker for deriv)
        def draw_val_ticks(vmin, vmax, color, side):
            if not math.isfinite(vmin) or not math.isfinite(vmax):
                return
            step = self._nice_step(vmax - vmin)
            start = math.floor(vmin / step) * step
            val = start
            painter.setPen(color)

            while val <= vmax + 1e-9:
                txt = self._fmt(val)
                if self.kind == 'x':  # Value is Horizontal
                    sx = map_lin(val, vmin, vmax, x0, x1)
                    if x0 - 1 <= sx <= x1 + 1:
                        if side == 'bottom':
                            painter.drawText(int(sx) - 10, int(y1) + 28, txt)
                        else:  # top
                            painter.drawText(int(sx) - 10, int(y0) - 8, txt)
                else:  # Value is Vertical
                    sy = map_lin(val, vmin, vmax, y1, y0)
                    if y0 - 1 <= sy <= y1 + 1:
                        if side == 'left':
                            painter.drawText(int(x0) - 42, int(sy) + 4, txt)
                        else:  # right
                            painter.drawText(int(x1) + 8, int(sy) + 4, txt)
                val += step

        # Get representative colors for main and deriv ticks
        main_tick_color = fg
        deriv_tick_color = fg
        for sys_id, tr in self.system_traces.items():
            if tr['show_main']:
                main_tick_color = tr['color']
                break
        for sys_id, tr in self.system_traces.items():
            if tr['show_deriv']:
                deriv_tick_color = QColor(int(tr['color'].red() * 0.7), int(tr['color'].green() * 0.7), int(tr['color'].blue() * 0.7))
                break

        # Main (lighter) -> Bottom (x) or Left (y)
        if has_main:
            draw_val_ticks(min_main, max_main, main_tick_color, 'bottom' if self.kind == 'x' else 'left')

        # Deriv (darker) -> Top (x) or Right (y)
        if has_deriv:
            draw_val_ticks(min_deriv, max_deriv, deriv_tick_color, 'top' if self.kind == 'x' else 'right')

        # Draw mean / ±σ annotations on the value axis
        self._draw_stats_annotations(
            painter, fg, x0, x1, y0, y1,
            group_main, group_deriv,
            min_main, max_main, has_main,
            min_deriv, max_deriv, has_deriv,
            map_lin, t_min, t_max
        )

        self._draw_legend(painter, fg, x0, y0)

    '''
    def _draw_legend(self, painter, fg, x0, y0):
        self.legend_rects.clear()
        font = QFont('Arial', 8)
        if self.dark_mode:
            font.setBold(True)
        painter.setFont(font)

        x_cursor = 8
        ytxt = 14
        var_name = 'x' if self.kind == 'x' else 'y'

        for sys_id, tr in self.system_traces.items():
            base_color = tr['color']
            label = tr['label'] or sys_id

            # Main trace label (lighter)
            lbl_main = f'{label}:{var_name}'
            kw = painter.fontMetrics().horizontalAdvance(lbl_main)
            col = base_color if tr['show_main'] else QColor(128, 128, 128, 100)
            painter.setPen(col)
            painter.drawText(x_cursor, ytxt, lbl_main)
            self.legend_rects[(sys_id, 'main')] = QRect(x_cursor, ytxt - 12, kw, 16)
            x_cursor += kw + 6

            # Deriv trace label (darker)
            lbl_deriv = f'd{var_name}/dt'
            kw = painter.fontMetrics().horizontalAdvance(lbl_deriv)
            deriv_color = QColor(int(base_color.red() * 0.7), int(base_color.green() * 0.7), int(base_color.blue() * 0.7))
            col = deriv_color if tr['show_deriv'] else QColor(128, 128, 128, 100)
            painter.setPen(col)
            painter.drawText(x_cursor, ytxt, lbl_deriv)
            self.legend_rects[(sys_id, 'deriv')] = QRect(x_cursor, ytxt - 12, kw, 16)
            x_cursor += kw + 12

        # Custom trace labels
        for i, tr in enumerate(self.custom_traces):
            lbl = tr['label']
            kw = painter.fontMetrics().horizontalAdvance(lbl)
            col = tr['color'] if tr['visible'] else QColor(128, 128, 128, 100)
            painter.setPen(col)
            painter.drawText(x_cursor, ytxt, lbl)
            self.legend_rects[i] = QRect(x_cursor, ytxt - 12, kw, 16)
            x_cursor += kw + 8
    '''
    def _draw_legend(self, painter, fg, x0, y0):
        self.legend_rects.clear()
        font = QFont('Arial', 8)
        if self.dark_mode:
            font.setBold(True)
        painter.setFont(font)

        x_cursor = 8
        ytxt = 14
        var_name = 'x' if self.kind == 'x' else 'y'

        # Group traces by system_id (stored in trace label or parent lookup)
        # We need to get system info from parent canvas
        canvas = self.parent()
        if not canvas:
            return

        # Draw one legend entry per system
        for system in canvas.systems:
            base_color = system.color
            label = system.name

            # Check if any particle of this system has show_main/show_deriv enabled
            show_main = False
            show_deriv = False
            for p in canvas.particles:
                if p.system_id == system.uid and p.uid in self.system_traces:
                    tr = self.system_traces[p.uid]
                    if tr['show_main']:
                        show_main = True
                    if tr['show_deriv']:
                        show_deriv = True

            # Main trace label
            lbl_main = f'{label}:{var_name}'
            kw = painter.fontMetrics().horizontalAdvance(lbl_main)
            col = base_color if show_main else QColor(128, 128, 128, 100)
            painter.setPen(col)
            painter.drawText(x_cursor, ytxt, lbl_main)
            self.legend_rects[(system.uid, 'main')] = QRect(x_cursor, ytxt - 12, kw, 16)
            x_cursor += kw + 6

            # Deriv trace label
            lbl_deriv = f'd{var_name}/dt'
            kw = painter.fontMetrics().horizontalAdvance(lbl_deriv)
            deriv_color = QColor(int(base_color.red() * 0.7), int(base_color.green() * 0.7), int(base_color.blue() * 0.7))
            col = deriv_color if show_deriv else QColor(128, 128, 128, 100)
            painter.setPen(col)
            painter.drawText(x_cursor, ytxt, lbl_deriv)
            self.legend_rects[(system.uid, 'deriv')] = QRect(x_cursor, ytxt - 12, kw, 16)
            x_cursor += kw + 12

        # Custom trace labels (unchanged)
        for i, tr in enumerate(self.custom_traces):
            lbl = tr['label']
            kw = painter.fontMetrics().horizontalAdvance(lbl)
            col = tr['color'] if tr['visible'] else QColor(128, 128, 128, 100)
            painter.setPen(col)
            painter.drawText(x_cursor, ytxt, lbl)
            self.legend_rects[i] = QRect(x_cursor, ytxt - 12, kw, 16)
            x_cursor += kw + 8

    def _draw_stats_annotations(self, painter, fg, x0, x1, y0, y1,
                                 group_main, group_deriv,
                                 min_main, max_main, has_main,
                                 min_deriv, max_deriv, has_deriv,
                                 map_lin, t_min, t_max):
        """Draw per-curve mean (solid line) and ±1 std-dev (dashed lines) on
        the value axis.  Each curve gets its own annotation drawn in its own
        color, so with N visible curves there are N sets of lines.
        """

        def _stats_for_item(item):
            """Return (mean, std) for a single trace item.

            Windowed mode  → use the pts already stored in item['pts'].
            Full-history   → fetch the complete deque from system_traces /
                             custom_traces so statistics go back to t=0.
            """
            trace_type = item.get('type')
            if self.stats_use_full_history and trace_type in ('main', 'deriv'):
                tr = self.system_traces.get(item['sys_id'])
                if tr is None:
                    return None, None
                if trace_type == 'main':
                    vals = [v for _, v in tr['main_samples']]
                else:
                    vals = [v for _, v in self._finite_diff(list(tr['main_samples']))]
            elif self.stats_use_full_history and trace_type == 'custom':
                item_color = item['color']
                vals = []
                for ct in self.custom_traces:
                    if ct['visible'] and ct['color'] == item_color:
                        vals = [v for _, v in ct['samples']]
                        break
            else:
                vals = [p[1] for p in item['pts']]

            if not vals:
                return None, None
            arr = np.array(vals, dtype=float)
            arr = arr[np.isfinite(arr)]
            if len(arr) == 0:
                return None, None
            return float(np.mean(arr)), float(np.std(arr))

        def _draw_annotation(mean, std, color, vmin, vmax):
            """Draw mean (solid) and ±σ (dashed) lines for one curve."""
            if mean is None:
                return

            mean_color = QColor(color)
            mean_color.setAlpha(200)
            band_color = QColor(color)
            band_color.setAlpha(110)

            def val_to_screen(v):
                if self.kind == 'x':
                    return map_lin(v, vmin, vmax, x0, x1)
                else:
                    return map_lin(v, vmin, vmax, y1, y0)

            sv_mean = val_to_screen(mean)

            # mean line
            pen = QPen(mean_color)
            pen.setWidth(1)
            pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            if self.kind == 'x':
                if x0 <= sv_mean <= x1:
                    painter.drawLine(QPointF(sv_mean, y0), QPointF(sv_mean, y1))
            else:
                if y0 <= sv_mean <= y1:
                    painter.drawLine(QPointF(x0, sv_mean), QPointF(x1, sv_mean))

            # ±σ lines
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setColor(band_color)
            painter.setPen(pen)
            for sign in (+1, -1):
                sv = val_to_screen(mean + sign * std)
                if self.kind == 'x':
                    if x0 <= sv <= x1:
                        painter.drawLine(QPointF(sv, y0), QPointF(sv, y1))
                else:
                    if y0 <= sv <= y1:
                        painter.drawLine(QPointF(x0, sv), QPointF(x1, sv))

            # text labels
            painter.setFont(QFont('Courier', 7))
            lbl_color = QColor(mean_color)
            lbl_color.setAlpha(230)
            painter.setPen(lbl_color)
            lbl_mean = f'μ={self._fmt(mean)}'
            lbl_std  = f'σ={self._fmt(std)}'

            if self.kind == 'x':
                if x0 <= sv_mean <= x1:
                    painter.drawText(int(sv_mean) - 16, int(y1) + 40, lbl_mean)
                sv_plus = val_to_screen(mean + std)
                if x0 <= sv_plus <= x1:
                    painter.drawText(int(sv_plus) - 14, int(y1) + 50, lbl_std)
            else:
                offset_x = int(x1) + 8
                if y0 <= sv_mean <= y1:
                    painter.drawText(offset_x, int(sv_mean) - 2, lbl_mean)
                sv_plus = val_to_screen(mean + std)
                if y0 <= sv_plus <= y1:
                    painter.drawText(offset_x, int(sv_plus) - 2, lbl_std)

        # Draw one annotation per curve, in that curve's own color.
        if has_main:
            for item in group_main:
                mean_v, std_v = _stats_for_item(item)
                _draw_annotation(mean_v, std_v, item['color'], min_main, max_main)

        if has_deriv:
            for item in group_deriv:
                mean_v, std_v = _stats_for_item(item)
                _draw_annotation(mean_v, std_v, item['color'], min_deriv, max_deriv)


class CalculatorOverlay(QWidget):
    """Overlay for analysing functions, like variance, mean..."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._bg_alpha = 185
        self.dark_mode = True

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # First row: particle ID + expression inputs
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.particle_input = QLineEdit()
        self.particle_input.setPlaceholderText("Particle ID")
        self.particle_input.setFixedWidth(80)
        self.particle_input.textChanged.connect(self._on_input_changed)
        input_row.addWidget(self.particle_input)

        self.expr_input = QLineEdit()
        self.expr_input.setPlaceholderText("Expression (e.g., mean(x), var(y))")
        self.expr_input.textChanged.connect(self._on_input_changed)
        input_row.addWidget(self.expr_input)

        layout.addLayout(input_row)

        # Second row: result label
        self.result_label = QLabel("Result: —")
        self.result_label.setStyleSheet("color: #aaffaa; font-weight: bold;")
        layout.addWidget(self.result_label)

        layout.addStretch()

        # Compiled function and target particle
        self._compiled_fn = None
        self._target_particle_uid = None

    def set_dark_mode(self, v: bool):
        self.dark_mode = bool(v)
        color = "#aaffaa" if self.dark_mode else "#006600"
        self.result_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.update()

    def _on_input_changed(self):
        """Recompile expression when inputs change."""
        self._target_particle_uid = self.particle_input.text().strip() or None
        expr = self.expr_input.text().strip()

        if not expr:
            self._compiled_fn = None
            self.result_label.setText("Result: —")
            return

        try:
            # Build environment with statistical functions
            env = self._build_stat_env()
            self._compiled_fn = compile_expr(expr, extra_names=env)
            self.result_label.setText("Result: ...")
        except Exception as e:
            self._compiled_fn = None
            self.result_label.setText(f"Error: {e}")

    def _build_stat_env(self):
        """Build environment with statistical functions for the target particle."""
        canvas = self.parent()
        if not canvas:
            return {}

        particle = self._get_target_particle()
        if not particle:
            return {}

        # Get x and y history samples - history contains (t, x, y) tuples
        history = list(particle.history)
        t_now = history[-1][0] if history else 0.0

        def filter_samples(samples, T=None):
            if T is None:
                return samples
            try:
                T_val = float(T)
            except Exception:
                T_val = 0.0
            t_min = t_now - T_val
            # Always return a list of (t, v) tuples
            return [(t, v) for (t, v) in samples if t >= t_min]

        x_samples_all = [(entry[0], entry[1]) for entry in history]
        y_samples_all = [(entry[0], entry[2]) for entry in history]

        def mean_x(T=None):
            xs = filter_samples(x_samples_all, T)
            vals = [v for (_, v) in xs]
            return sum(vals) / len(vals) if vals else 0.0

        def mean_y(T=None):
            ys = filter_samples(y_samples_all, T)
            vals = [v for (_, v) in ys]
            return sum(vals) / len(vals) if vals else 0.0

        def var_x(T=None):
            xs = filter_samples(x_samples_all, T)
            vals = [v for (_, v) in xs]
            if len(vals) < 2:
                return 0.0
            m = sum(vals) / len(vals)
            return sum((v - m) ** 2 for v in vals) / len(vals)

        def var_y(T=None):
            ys = filter_samples(y_samples_all, T)
            vals = [v for (_, v) in ys]
            if len(vals) < 2:
                return 0.0
            m = sum(vals) / len(vals)
            return sum((v - m) ** 2 for v in vals) / len(vals)

        def std_x(T=None):
            return math.sqrt(var_x(T))

        def std_y(T=None):
            return math.sqrt(var_y(T))

        def min_x(T=None):
            xs = filter_samples(x_samples_all, T)
            vals = [v for (_, v) in xs]
            return min(vals) if vals else 0.0

        def max_x(T=None):
            xs = filter_samples(x_samples_all, T)
            vals = [v for (_, v) in xs]
            return max(vals) if vals else 0.0

        def min_y(T=None):
            ys = filter_samples(y_samples_all, T)
            vals = [v for (_, v) in ys]
            return min(vals) if vals else 0.0

        def max_y(T=None):
            ys = filter_samples(y_samples_all, T)
            vals = [v for (_, v) in ys]
            return max(vals) if vals else 0.0

        def n_x(T=None):
            xs = filter_samples(x_samples_all, T)
            return len(xs)

        def n_y(T=None):
            ys = filter_samples(y_samples_all, T)
            return len(ys)

        return {
            'mean_x': mean_x, 'mean_y': mean_y,
            'var_x': var_x, 'var_y': var_y,
            'std_x': std_x, 'std_y': std_y,
            'min_x': min_x, 'max_x': max_x,
            'min_y': min_y, 'max_y': max_y,
            'n_x': n_x, 'n_y': n_y,
        }
    def _get_target_particle(self):
        """Get the particle matching the target UID."""
        canvas = self.parent()
        if not canvas or not self._target_particle_uid:
            return None

        for p in canvas.particles:
            if p.uid == self._target_particle_uid or p.name == self._target_particle_uid:
                return p
        return None

    def update_result(self):
        """Called each frame to update the result in real-time."""
        if not self._compiled_fn:
            return

        particle = self._get_target_particle()
        if not particle:
            self.result_label.setText("Result: Particle not found")
            return

        try:
            # Rebuild env with current data and evaluate
            env = self._build_stat_env()
            # Re-compile with fresh data
            expr = self.expr_input.text().strip()
            fn = compile_expr(expr, extra_names=env)
            result = fn(particle.x, particle.y, self.parent().t if self.parent() else 0.0)
            self.result_label.setText(f"Result: {result:.6g}")
        except Exception as e:
            self.result_label.setText(f"Error: {e}")

    def paintEvent(self, ev):
        painter = QPainter(self)
        if self.dark_mode:
            bg = QColor(8, 10, 14, self._bg_alpha)
        else:
            bg = QColor(255, 255, 255, self._bg_alpha)
        painter.fillRect(self.rect(), bg)




# --------------------- Safe expression compilation ---------------------
ALLOWED_NAMES = {
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
    'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
    'exp': math.exp, 'log': math.log, 'log10': math.log10,
    'sqrt': math.sqrt, 'abs': abs, 'pow': pow,
    'pi': math.pi, 'e': math.e,
    'floor': math.floor, 'ceil': math.ceil,
}
# Add deprecated ast.Num for Python < 3.14 compatibility


class _StateAccessor:
    """Callable proxy that supports x(t) / x(t-τ) syntax.

    The simulator injects these objects as 'x' and 'y' when evaluating expressions.

    - When used as a number (e.g., x + 1), it behaves like the current state value.
    - When called like x(t) or x(t-τ), it returns a past value from a history provider.

    History provider contract: get_state_at(var: str, query_t: float, default: float) -> float
    """

    __slots__ = ('_var', '_current', '_get_state_at', '_default')

    def __init__(self, var: str, current: float, get_state_at, default: float):
        self._var = var
        self._current = float(current)
        self._get_state_at = get_state_at
        self._default = float(default)

    def __float__(self):
        return float(self._current)

    def __int__(self):
        return int(self._current)

    def _v(self):
        return float(self._current)

    def __add__(self, other):
        return self._v() + other

    def __radd__(self, other):
        return other + self._v()

    def __sub__(self, other):
        return self._v() - other

    def __rsub__(self, other):
        return other - self._v()

    def __mul__(self, other):
        return self._v() * other

    def __rmul__(self, other):
        return other * self._v()

    def __truediv__(self, other):
        return self._v() / other

    def __rtruediv__(self, other):
        return other / self._v()

    def __pow__(self, other):
        return self._v() ** other

    def __rpow__(self, other):
        return other ** self._v()

    def __neg__(self):
        return -self._v()

    def __pos__(self):
        return +self._v()

    def __abs__(self):
        return abs(self._v())

    def __repr__(self):
        return f"{self._var}={self._current:g}"

    def __call__(self, query_t=None):
        if query_t is None:
            return float(self._current)
        try:
            qt = float(query_t)
        except Exception:
            qt = float('nan')
        return float(self._get_state_at(self._var, qt, self._default))


class TwoStateGate:
    """A continuous-time two-state process G(t) ∈ {0,1}.

    Transition probabilities for a small timestep dt:
      P(0→1) = kon * dt
      P(1→0) = koff * dt

    This is integrated with an exact Bernoulli update per step (clamped to [0,1]).
    The object is callable so it can be used in expressions as G(t) or just G().
    """

    def __init__(self, kon: float, koff: float, initial: int = 0, name: str | None = None):
        self.kon = float(kon)
        self.koff = float(koff)
        self.state = 1 if int(initial) else 0
        self.name = name

    def reset(self, initial: int = 0):
        self.state = 1 if int(initial) else 0

    def step(self, dt: float, rng: random.Random | None = None):
        rng = rng or random
        dt = max(0.0, float(dt))
        if self.state == 0:
            p = self.kon * dt
            if p >= 1.0:
                self.state = 1
            elif p > 0.0 and rng.random() < p:
                self.state = 1
        else:
            p = self.koff * dt
            if p >= 1.0:
                self.state = 0
            elif p > 0.0 and rng.random() < p:
                self.state = 0

    def __call__(self, *args):
        return float(self.state)

    def __repr__(self) -> str:
        return f"TwoStateGate(kon={self.kon}, koff={self.koff}, state={self.state})"


class StepFunction:
    """A periodic step function S(t) ∈ {0,1}.

    The function alternates between 0 and 1:
      - Starts at 0
      - Stays at 0 for dt0 seconds
      - Switches to 1 for dt1 seconds
      - Repeats with period = dt0 + dt1

    The object is callable so it can be used in expressions as S(t) or just S().
    When called without arguments, it uses the current simulation time.
    """

    def __init__(self, dt0: float, dt1: float, name: str | None = None):
        self.dt0 = max(0.001, float(dt0))  # Time spent at 0
        self.dt1 = max(0.001, float(dt1))  # Time spent at 1
        self.period = self.dt0 + self.dt1
        self.name = name
        self._current_t = 0.0  # Track current simulation time

    def reset(self):
        self._current_t = 0.0

    def update_time(self, t: float):
        """Update the current simulation time."""
        self._current_t = float(t)

    def value_at(self, t: float) -> float:
        """Get the step function value at time t."""
        t = float(t)
        if t < 0:
            t = 0.0
        # Find position within the current period
        phase = t % self.period
        # If we're in the first dt0 seconds of the period, value is 0
        # Otherwise (in the dt1 portion), value is 1
        if phase < self.dt0:
            return 0.0
        else:
            return 1.0

    def __call__(self, t=None):
        if t is None:
            return self.value_at(self._current_t)
        return self.value_at(float(t))

    def __repr__(self) -> str:
        return f"StepFunction(dt0={self.dt0}, dt1={self.dt1})"


class SmoothStepFunction:
    """A periodic smooth step function with sigmoid transitions.

    The function alternates between 0 and 1 with smooth transitions:
      - Starts at 0
      - Stays at 0 for dt0 seconds
      - Smoothly rises to 1 (with steepness controlled by k_rise)
      - Stays at 1 for dt1 seconds
      - Smoothly falls to 0 (with steepness controlled by k_fall)
      - Repeats with period = dt0 + dt1

    Parameters:
      dt0: Duration at 0 value
      dt1: Duration at 1 value
      k_rise: Steepness of the rising edge (higher = sharper transition)
      k_fall: Steepness of the falling edge (higher = sharper transition)

    The object is callable so it can be used in expressions as S(t) or just S().
    When called without arguments, it uses the current simulation time.
    """

    def __init__(self, dt0: float, dt1: float, k_rise: float = 10.0, k_fall: float = 10.0, name: str | None = None):
        self.dt0 = max(0.001, float(dt0))  # Time spent at 0
        self.dt1 = max(0.001, float(dt1))  # Time spent at 1
        self.k_rise = max(0.1, float(k_rise))  # Steepness of rise
        self.k_fall = max(0.1, float(k_fall))  # Steepness of fall
        self.period = self.dt0 + self.dt1
        self.name = name
        self._current_t = 0.0  # Track current simulation time

    def reset(self):
        self._current_t = 0.0

    def update_time(self, t: float):
        """Update the current simulation time."""
        self._current_t = float(t)

    def value_at(self, t: float) -> float:
        """Get the smooth step function value at time t using sigmoid transitions."""
        t = float(t)
        if t < 0:
            t = 0.0

        # Find position within the current period
        phase = t % self.period

        # Use sigmoid transitions at the boundaries
        # The sigmoid function 1/(1+exp(-k*x)) transitions from 0 to 1
        # We'll use a transition region based on where we want smooth edges

        # Transition width is determined by k values (smaller k = wider transition)
        # A reasonable transition width is about 6/k for the sigmoid to go from ~0.01 to ~0.99
        fall_width = min(self.dt0 * 0.5, 6.0 / max(0.1, self.k_fall))
        rise_width = min(self.dt1 * 0.5, 6.0 / max(0.1, self.k_rise))

        # Check if we're in the falling edge (end of previous high period, start of low period)
        if phase < fall_width:
            # Falling edge: transition from 1 to 0
            # Map phase [0, fall_width] to x [-3, 3] for sigmoid
            x = (phase / fall_width) * 6.0 - 3.0
            return 1.0 / (1.0 + math.exp(self.k_fall * x))

        # Check if we're in the low period (after falling edge, before rising edge)
        elif phase < self.dt0 - rise_width:
            return 0.0

        # Check if we're in the rising edge (end of low period, start of high period)
        elif phase < self.dt0 + rise_width:
            # Rising edge: transition from 0 to 1
            # Map the transition region to x [-3, 3] for sigmoid
            phase_in_transition = phase - (self.dt0 - rise_width)
            x = (phase_in_transition / (2.0 * rise_width)) * 6.0 - 3.0
            return 1.0 / (1.0 + math.exp(-self.k_rise * x))

        # We're in the high period (after rising edge)
        else:
            return 1.0

    def __call__(self, t=None):
        if t is None:
            return self.value_at(self._current_t)
        return self.value_at(float(t))

    def __repr__(self) -> str:
        return f"SmoothStepFunction(dt0={self.dt0}, dt1={self.dt1}, k_rise={self.k_rise}, k_fall={self.k_fall})"


ALLOWED_NODE_TYPES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Constant,
    ast.Name, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub,
    ast.UAdd, ast.Mod,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.BoolOp, ast.And, ast.Or,
    ast.IfExp,
}

def _validate_identifier(name: str) -> str:
    name = (name or '').strip()
    if not name:
        raise ValueError('Name is empty')
    if not name.isidentifier():
        raise ValueError(f'Invalid identifier: {name}')
    if name in ('x', 'y', 't'):
        raise ValueError(f'Name "{name}" is reserved')
    if name in ALLOWED_NAMES:
        raise ValueError(f'Name "{name}" conflicts with a built-in function/constant')
    return name


def compile_expr(expr_text: str, extra_names=None):
    """Compile an expression like 'x - y' into a function f(x,y,t)."""
    expr_text = (expr_text or '').strip()
    if expr_text == '':
        raise ValueError('Empty expression')

    extra_names = dict(extra_names or {})

    # Wrap user-provided callables so calling conventions are flexible
    wrapped_extra = {}
    for k, v in extra_names.items():
        if callable(v):
            def _make_wrapper(fn):
                def _w(*args):
                    if len(args) == 1:
                        return fn(args[0])
                    if len(args) == 3:
                        return fn(args[0], args[1], args[2])
                    return fn(*args)
                return _w
            wrapped_extra[k] = _make_wrapper(v)
        else:
            wrapped_extra[k] = v

    try:
        node = ast.parse(expr_text, mode='eval')
    except Exception as e:
        raise ValueError(f'Parse error: {e}')

    for sub in ast.walk(node):
        if not isinstance(sub, tuple(ALLOWED_NODE_TYPES)):
            raise ValueError(f'Illegal expression element: {type(sub).__name__}')
        if isinstance(sub, ast.Name):
            if sub.id not in ('x', 'y', 't', 'dt') and sub.id not in ALLOWED_NAMES and sub.id not in wrapped_extra:
                raise ValueError(f'Unknown name: {sub.id}')
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                fn_name = sub.func.id
                if fn_name in ALLOWED_NAMES:
                    pass
                elif fn_name in wrapped_extra and callable(wrapped_extra[fn_name]):
                    pass
                elif fn_name in ('x', 'y'):
                    pass
                else:
                    raise ValueError(f'Illegal function: {fn_name}')
            else:
                raise ValueError('Only bare function calls allowed')

    compiled = compile(node, '<string>', 'eval')

    def f(x, y, t, dt: float = 0.0, state_provider=None):
        def _fallback_get_state_at(var: str, query_t: float, default: float):
            if var == 'x':
                return float(x)
            if var == 'y':
                return float(y)
            return float(default)

        getter = state_provider or _fallback_get_state_at
        local = {
            'x': _StateAccessor('x', x, getter, x),
            'y': _StateAccessor('y', y, getter, y),
            't': t,
            'dt': dt,
        }
        local.update(ALLOWED_NAMES)
        local.update(wrapped_extra)
        return eval(compiled, {'__builtins__': {}}, local)

    return f


def _compile_definition_expr(expr_text: str, extra_names=None):
    """Compile a definition expression into g(t)."""
    g = compile_expr(expr_text, extra_names=extra_names)

    def gt(t):
        return g(0.0, 0.0, t)

    return gt


# --------------------- Particle / Simulation data structures ---------------------

COLOR_PALETTE = [
    '#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00', '#a65628', '#f781bf', '#999999'
]

SYSTEM_COLORS = [
    '#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c', '#e91e63', '#00bcd4'
]


class Particle:
    def __init__(self, x0, y0, color=None, name=None, system_id=None):
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.x = float(x0)
        self.y = float(y0)
        self.history = deque()
        self.max_history_time = 500.0
        self.color = QColor(color) if color else QColor(random.choice(COLOR_PALETTE))
        self.name = name or f'p{random.randint(0, 9999)}'
        self.running = False
        self.age = 0.0
        self.system_id = system_id  # Which system this particle belongs to
        self.uid = f'{time.time_ns()}_{random.randint(0, 1_000_000)}'
        self.hiden = False

        self.custom_vars = {}  # dict of var_name -> value (float)

    def get_state_at(self, var: str, query_t: float, default: float) -> float:
        """Get state value at a specific time from history using linear interpolation.

        Args:
            var: Variable name ('x' or 'y')
            query_t: Time at which to query the state
            default: Default value if time is outside history range

        Returns:
            Interpolated state value at query_t
        """
        if not self.history:
            return float(default)

        # history format: (t, x, y, vx, vy)
        var_idx = 1 if var == 'x' else 2  # x is index 1, y is index 2

        # If query time is before first history point, return default
        if query_t < self.history[0][0]:
            return float(default)

        # If query time is at or after last history point, return last value
        if query_t >= self.history[-1][0]:
            return float(self.history[-1][var_idx])

        # Binary search for the right interval
        left, right = 0, len(self.history) - 1
        while left < right - 1:
            mid = (left + right) // 2
            if self.history[mid][0] <= query_t:
                left = mid
            else:
                right = mid

        # Linear interpolation between history[left] and history[right]
        t0, x0, y0, _, _ = self.history[left]
        t1, x1, y1, _, _ = self.history[right]

        if abs(t1 - t0) < 1e-12:
            # Times are too close, just return the value at left
            return float(self.history[left][var_idx])

        # Interpolate
        alpha = (query_t - t0) / (t1 - t0)
        v0 = self.history[left][var_idx]
        v1 = self.history[right][var_idx]

        return float(v0 + alpha * (v1 - v0))

    def step(self, vx, vy, dt, t):
        self.x += vx * dt
        self.y += vy * dt
        self.history.append((t, self.x, self.y, vx, vy))
        self.age = t
        while self.history and (t - self.history[0][0] > self.max_history_time):
            self.history.popleft()

    def reset_history(self):
        self.history.clear()
        self.history.append((0.0, self.x, self.y, 0.0, 0.0))

    def reset(self):
        self.x = float(self.x0)
        self.y = float(self.y0)
        self.age = 0.0
        self.running = False
        self.reset_history()


class DynamicalSystem:
    """Represents a single dynamical system with its own equations, color, and particles."""

    def __init__(self, name: str = None, dx_expr: str = 'x', dy_expr: str = 'y', color: str = None):
        self.uid = f'{time.time_ns()}_{random.randint(0, 1_000_000)}'
        self.name = name or f'System {random.randint(1, 999)}'
        self.dx_expr = dx_expr
        self.dy_expr = dy_expr
        self.color = QColor(color) if color else QColor(random.choice(SYSTEM_COLORS))

        # Visibility toggles
        self.show_arrows = True
        self.show_particles = True
        self.show_overlay = True

        # Compiled functions
        self.dx_fn = None
        self.dy_fn = None
        self.model_env = {}

        self.compile_equations()

    def compile_equations(self):
        """Compile equations - they will receive custom_vars at evaluation time."""
        try:
            self.dx_fn = self._make_evaluator(self.dx_expr)
            self.dy_fn = self._make_evaluator(self.dy_expr)
        except Exception:
            self.dx_fn = None
            self.dy_fn = None

    def _make_evaluator(self, expr_text: str):
        """Create an evaluator that accepts custom_vars at runtime."""
        expr_text = (expr_text or '').strip()
        if not expr_text:
            return lambda x, y, t, dt=0.0, state_provider=None, custom_vars=None: 0.0

        try:
            node = ast.parse(expr_text, mode='eval')
        except Exception:
            return lambda x, y, t, dt=0.0, state_provider=None, custom_vars=None: 0.0

        # Skip strict validation since custom_vars are injected at runtime
        # Just check for obviously dangerous nodes
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Import, ast.ImportFrom, ast.Attribute)):
                return lambda x, y, t, dt=0.0, state_provider=None, custom_vars=None: 0.0

        try:
            compiled = compile(node, '<string>', 'eval')
        except Exception:
            return lambda x, y, t, dt=0.0, state_provider=None, custom_vars=None: 0.0

        model_env = self.model_env

        def evaluator(x, y, t, dt=0.0, state_provider=None, custom_vars=None):
            def _fallback(var, query_t, default):
                return default

            getter = state_provider or _fallback
            local = {
                'x': _StateAccessor('x', x, getter, x),
                'y': _StateAccessor('y', y, getter, y),
                't': t,
                'dt': dt,
            }
            local.update(ALLOWED_NAMES)
            local.update(model_env)
            if custom_vars:
                local.update(custom_vars)
            try:
                result = eval(compiled, {'__builtins__': {}}, local)
                return float(result) if result is not None else 0.0
            except Exception:
                return 0.0

        return evaluator

    def eval_dxdy(self, x: float, y: float, t: float, dt: float = 0.0, state_provider=None, custom_vars: dict = None):
        try:
            vx = self.dx_fn(x, y, t, dt, state_provider, custom_vars) if self.dx_fn else 0.0
        except Exception:
            vx = 0.0
        try:
            vy = self.dy_fn(x, y, t, dt, state_provider, custom_vars) if self.dy_fn else 0.0
        except Exception:
            vy = 0.0
        if not math.isfinite(vx):
            vx = 0.0
        if not math.isfinite(vy):
            vy = 0.0
        return vx, vy

    def to_dict(self):
        return {
            'uid': self.uid,
            'name': self.name,
            'dx_expr': self.dx_expr,
            'dy_expr': self.dy_expr,
            'color': self.color.name(),
            'show_arrows': self.show_arrows,
            'show_particles': self.show_particles,
            'show_overlay': self.show_overlay,
        }

    @classmethod
    def from_dict(cls, data: dict):
        sys = cls(
            name=data.get('name', 'System'),
            dx_expr=data.get('dx_expr', 'x'),
            dy_expr=data.get('dy_expr', 'y'),
            color=data.get('color')
        )
        sys.uid = data.get('uid', sys.uid)
        sys.show_arrows = data.get('show_arrows', True)
        sys.show_particles = data.get('show_particles', True)
        sys.show_overlay = data.get('show_overlay', True)
        return sys


# --------------------- Canvas Widget ---------------------

class PhaseCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 600)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.mouse_pos = (0.0, 0.0)

        # world transform
        self.scale = 60.0
        self.offset = np.array([0.0, 0.0])

        self.pan_last = None
        self.show_values = True
        self.dark_mode = True

        # Multiple dynamical systems
        self.systems: list[DynamicalSystem] = []
        self.active_system_uid: str = None  # For placing particles

        # Two-state gates (stochastic 0/1 variables)
        self.gates: dict[str, TwoStateGate] = {}

        # Periodic step functions
        self.step_functions: dict[str, StepFunction] = {}

        # Model environment for user-defined functions/constants
        self.model_env = {}

        # All particles (each knows its system_id)
        self.particles: list[Particle] = []

        # vector field display density
        self.grid_density = 20

        self.placing_mode = False

        # simulation
        self.t = 0.0
        self.dt = 0.02
        self.time_scale = 1.0

        self.timer = QTimer()
        self.timer.timeout.connect(self.on_frame)
        self.timer.start(int(1000 / 60))

        self.last_frame_time = time.time()
        self.simulation_running = False

        # caching
        self.field_cache = {}
        self.field_cache_scale = None
        self.field_cache_offset = None
        self.field_cache_t = None

        # Axis labels
        self.x_axis_name = 'x'
        self.y_axis_name = 'y'
        self.x_axis_unit = ''
        self.y_axis_unit = ''

        self.show_ticks = True
        self.tick_target_px = 80

        self.axis_margin_left = 54
        self.axis_margin_top = 28
        self.axis_margin_bottom = 34
        self.axis_margin_right = 18

        self.active_particle_uid = None

        # Overlays
        self.y_overlay = TimeGraphOverlay('y', self)
        self.y_overlay.hide()
        self.x_overlay = TimeGraphOverlay('x', self)
        self.x_overlay.hide()
        self.calc_overlay = CalculatorOverlay(self)
        self.calc_overlay.hide()


        self.btn_toggle_y = QToolButton(self)
        self.btn_toggle_y.setText('y')
        self.btn_toggle_y.setToolTip('Show/hide y(t) and dy/dt for all systems')
        self.btn_toggle_y.setCheckable(True)
        self.btn_toggle_y.setChecked(False)
        self.btn_toggle_y.setFixedSize(18, 18)
        self.btn_toggle_y.clicked.connect(self._on_toggle_y)

        self.btn_toggle_x = QToolButton(self)
        self.btn_toggle_x.setText('x')
        self.btn_toggle_x.setToolTip('Show/hide x(t) and dx/dt for all systems')
        self.btn_toggle_x.setCheckable(True)
        self.btn_toggle_x.setChecked(False)
        self.btn_toggle_x.setFixedSize(18, 18)
        self.btn_toggle_x.clicked.connect(self._on_toggle_x)

        self.btn_toggle_calc = QToolButton(self)
        self.btn_toggle_calc.setText('C')
        self.btn_toggle_calc.setToolTip('Show/hide Calculator widget')
        self.btn_toggle_calc.setCheckable(True)
        self.btn_toggle_calc.setChecked(False)
        self.btn_toggle_calc.setFixedSize(18, 18)
        self.btn_toggle_calc.clicked.connect(self._on_toggle_calc)

        self._relayout_overlays_and_buttons()

    def _on_toggle_y(self, checked: bool):
        self.y_overlay.setVisible(bool(checked))
        self._relayout_overlays_and_buttons()
        self.update()

    def _on_toggle_x(self, checked: bool):
        self.x_overlay.setVisible(bool(checked))
        self._relayout_overlays_and_buttons()
        self.update()

    def _on_toggle_calc(self, checked: bool):
        self.calc_overlay.setVisible(bool(checked))
        self._relayout_overlays_and_buttons()
        self.update()

    def add_system(self, system: DynamicalSystem):
        self.systems.append(system)
        self.x_overlay.add_system(system.uid, system.color, system.name)
        self.y_overlay.add_system(system.uid, system.color, system.name)
        if self.active_system_uid is None:
            self.active_system_uid = system.uid
        self.field_cache = {}

    def remove_system(self, system_uid: str):
        self.systems = [s for s in self.systems if s.uid != system_uid]
        self.particles = [p for p in self.particles if p.system_id != system_uid]
        self.x_overlay.remove_system(system_uid)
        self.y_overlay.remove_system(system_uid)
        if self.active_system_uid == system_uid:
            self.active_system_uid = self.systems[0].uid if self.systems else None
        self.field_cache = {}

    def get_system(self, uid: str) -> DynamicalSystem:
        for s in self.systems:
            if s.uid == uid:
                return s
        return None

    def _get_active_particle(self):
        uid = getattr(self, 'active_particle_uid', None)
        if uid:
            for p in self.particles:
                if getattr(p, 'uid', None) == uid:
                    return p
        for p in self.particles:
            if getattr(p, 'running', False):
                return p
        return self.particles[0] if self.particles else None

    def _relayout_overlays_and_buttons(self):
        w, h = self.width(), self.height()
        origin_sx, origin_sy = self.world_to_screen(0.0, 0.0)
        origin_sx = float(origin_sx)
        origin_sy = float(origin_sy)

        axis_x = max(0.0, min(float(w), origin_sx))
        axis_y = max(0.0, min(float(h), origin_sy))

        margin = 8

        y_left = margin
        y_top = margin
        y_right = max(y_left + 200, int(axis_x) - margin)
        y_bottom = max(y_top + 160, int(axis_y) - margin)
        self.y_overlay.setGeometry(y_left, y_top, max(10, y_right - y_left), max(10, y_bottom - y_top))

        x_left = min(w - margin - 10, int(axis_x) + margin)
        x_top = min(h - margin - 10, int(axis_y) + margin + 10)
        x_right = w - margin
        x_bottom = h - margin
        self.x_overlay.setGeometry(x_left, x_top, max(10, x_right - x_left), max(10, x_bottom - x_top))

        y_axis_x = int(axis_x)
        y_axis_x = max(2, min(w - 20, y_axis_x - 9))
        self.btn_toggle_y.move(y_axis_x, max(2, int(axis_y) - 30))

        x_axis_y = int(axis_y)
        x_axis_y = max(2, min(h - 20, x_axis_y - 9))
        self.btn_toggle_x.move(max(2, int(axis_x) + 12), x_axis_y)

        self.btn_toggle_calc.move(max(2, int(axis_x) - 20), x_axis_y + 12)
        self.calc_overlay.setGeometry(max(2, int(axis_x) - 320), x_axis_y + 30, 300, 100)

        self.y_overlay.set_dark_mode(self.dark_mode)
        self.x_overlay.set_dark_mode(self.dark_mode)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout_overlays_and_buttons()

    def world_to_screen(self, wx, wy):
        w, h = self.width(), self.height()
        sx = (wx - self.offset[0]) * self.scale + w / 2
        sy = (wy - self.offset[1]) * -self.scale + h / 2
        return sx, sy

    def screen_to_world(self, sx, sy):
        w, h = self.width(), self.height()
        wx = (sx - w / 2) / self.scale + self.offset[0]
        wy = - (sy - h / 2) / self.scale + self.offset[1]
        return wx, wy

    def set_axis_labels(self, x_name: str, y_name: str, x_unit: str = '', y_unit: str = ''):
        self.x_axis_name = (x_name or 'x').strip()
        self.y_axis_name = (y_name or 'y').strip()
        self.x_axis_unit = (x_unit or '').strip()
        self.y_axis_unit = (y_unit or '').strip()
        self._relayout_overlays_and_buttons()
        self.update()

    def _nice_tick_step(self, world_span: float, pixel_span: float) -> float:
        if world_span <= 0 or pixel_span <= 0:
            return 1.0
        target_world = (self.tick_target_px / max(1.0, pixel_span)) * world_span
        if target_world <= 0:
            return 1.0
        exp10 = math.floor(math.log10(target_world))
        base = 10 ** exp10
        for m in (1.0, 2.0, 5.0, 10.0):
            step = m * base
            if step >= target_world:
                return step
        return 10.0 * base

    def _format_tick(self, v: float) -> str:
        if abs(v) < 1e-12:
            v = 0.0
        av = abs(v)
        if av >= 1000 or (av > 0 and av < 0.01):
            return f'{v:.2e}'
        if av >= 100:
            return f'{v:.0f}'
        if av >= 10:
            return f'{v:.1f}'.rstrip('0').rstrip('.')
        return f'{v:.2f}'.rstrip('0').rstrip('.')

    def draw_axis_ticks_and_labels(self, painter: QPainter, wx_min, wx_max, wy_min, wy_max, fg: QColor):
        if not self.show_ticks:
            return

        w, h = self.width(), self.height()
        left = self.axis_margin_left
        right = w - self.axis_margin_right
        top = self.axis_margin_top
        bottom = h - self.axis_margin_bottom

        x_step = self._nice_tick_step(wx_max - wx_min, max(1.0, right - left))
        y_step = self._nice_tick_step(wy_max - wy_min, max(1.0, bottom - top))

        pen = QPen(QColor(fg))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setFont(QFont('Courier', 9))

        tick_len = 5

        if wy_min <= 0.0 <= wy_max:
            y_axis_screen = self.world_to_screen(0, 0)[1]
            y_axis_screen = min(max(y_axis_screen, top), bottom)
        else:
            y_axis_screen = bottom

        x_start = math.floor(wx_min / x_step) * x_step
        x_end = math.ceil(wx_max / x_step) * x_step
        x = x_start
        while x <= x_end + 1e-12:
            sx, _ = self.world_to_screen(x, 0.0)
            if left <= sx <= right:
                painter.drawLine(QPointF(sx, y_axis_screen - tick_len), QPointF(sx, y_axis_screen + tick_len))
                if abs(x) > 1e-12:
                    lbl = self._format_tick(x)
                    painter.drawText(int(sx) + 2, int(y_axis_screen) + 14, lbl)
            x += x_step

        if wx_min <= 0.0 <= wx_max:
            x_axis_screen = self.world_to_screen(0, 0)[0]
            x_axis_screen = min(max(x_axis_screen, left), right)
        else:
            x_axis_screen = left

        y_start = math.floor(wy_min / y_step) * y_step
        y_end = math.ceil(wy_max / y_step) * y_step
        y = y_start

        label_x = x_axis_screen + 8 if (wx_min <= 0.0 <= wx_max) else 2

        while y <= y_end + 1e-12:
            _, sy = self.world_to_screen(0.0, y)
            if top <= sy <= bottom:
                painter.drawLine(QPointF(x_axis_screen - tick_len, sy), QPointF(x_axis_screen + tick_len, sy))
                lbl = self._format_tick(y)
                painter.drawText(int(label_x), int(sy) - 2, lbl)
            y += y_step

        x_label = self.x_axis_name
        y_label = self.y_axis_name
        if self.x_axis_unit:
            x_label = f'{x_label} ({self.x_axis_unit})'
        if self.y_axis_unit:
            y_label = f'{y_label} ({self.y_axis_unit})'

        painter.setFont(QFont('Arial', 11))
        painter.drawText(int(right - 200), int(h - 8), x_label)

        y_label_x = 16
        y_anchor = top + 100

        painter.save()
        painter.translate(y_label_x, y_anchor)
        painter.rotate(-90)
        painter.drawText(0, 0, y_label)
        painter.restore()

    def paintEvent(self, ev):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.dark_mode:
            bg = QColor('#0f1115')
            fg = QColor('#dfe6f2')
        else:
            bg = QColor('#ffffff')
            fg = QColor('#111111')

        painter.fillRect(self.rect(), bg)

        w, h = self.width(), self.height()
        left_top = self.screen_to_world(0, 0)
        right_bottom = self.screen_to_world(w, h)
        wx_min = min(left_top[0], right_bottom[0])
        wx_max = max(left_top[0], right_bottom[0])
        wy_min = min(left_top[1], right_bottom[1])
        wy_max = max(left_top[1], right_bottom[1])

        # Draw vector fields for all visible systems
        for system in self.systems:
            if system.show_arrows:
                self.draw_vector_field(painter, wx_min, wx_max, wy_min, wy_max, system)

        # Draw axes
        pen = QPen(fg)
        pen.setWidth(1)
        painter.setPen(pen)
        sx1, sy1 = self.world_to_screen(wx_min, 0)
        sx2, sy2 = self.world_to_screen(wx_max, 0)
        painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
        sx1, sy1 = self.world_to_screen(0, wy_min)
        sx2, sy2 = self.world_to_screen(0, wy_max)
        painter.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))

        self.draw_axis_ticks_and_labels(painter, wx_min, wx_max, wy_min, wy_max, fg)

        # Draw particles for visible systems
        for p in self.particles:
            if p.hiden:
                continue
            system = self.get_system(p.system_id)
            # Draw particle if system is visible OR if system doesn't exist (orphan particle)
            if system is None or system.show_particles:
                self.draw_particle(painter, p)

        # Placing mode hint
        if self.placing_mode:
            pen = QPen(fg)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            active_sys = self.get_system(self.active_system_uid)
            sys_name = active_sys.name if active_sys else "No system"
            painter.drawText(10, 20, f'Placing mode ({sys_name}): click to add a point')

        # Values under cursor
        if self.show_values and hasattr(self, 'mouse_pos'):
            mx, my = self.mouse_pos
            wx, wy = self.screen_to_world(mx, my)

            info_lines = [f't={self.t:.3f}s   ({wx:.3f}, {wy:.3f})']
            for system in self.systems:
                if system.show_arrows:
                    vx, vy = system.eval_dxdy(wx, wy, self.t)
                    info_lines.append(f'{system.name}: (dx,dy)=({vx:.3f}, {vy:.3f})')

            painter.setPen(fg)
            painter.setFont(QFont('Courier', 9))
            y_pos = self.height() - 10 - (len(info_lines) - 1) * 14
            for line in info_lines:
                painter.drawText(10, y_pos, line)
                y_pos += 14

        self._relayout_overlays_and_buttons()

    def draw_particle(self, painter: QPainter, p: Particle):
        now = self.t
        trail = list(p.history)
        if len(trail) > 1:
            for i in range(len(trail) - 1):
                t0, x0, y0, vx0, vy0 = trail[i]
                t1, x1, y1, vx1, vy1 = trail[i + 1]
                age = now - t0
                alpha = max(0.0, 1.0 - age / p.max_history_time)
                pen = QPen(p.color)
                pen.setWidth(2)
                c = QColor(p.color)
                c.setAlphaF(alpha)
                pen.setColor(c)
                painter.setPen(pen)
                sx0, sy0 = self.world_to_screen(x0, y0)
                sx1, sy1 = self.world_to_screen(x1, y1)
                painter.drawLine(QPointF(sx0, sy0), QPointF(sx1, sy1))

        sx, sy = self.world_to_screen(p.x, p.y)
        r = max(4, 3 + int(self.scale * 0.02))
        brush = QBrush(p.color)
        painter.setBrush(brush)
        pen = QPen(QColor(0, 0, 0, 120))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(sx, sy), r, r)

    def draw_vector_field(self, painter, wx_min, wx_max, wy_min, wy_max, system: DynamicalSystem):
        w, h = self.width(), self.height()
        aspect = w / h
        nx = max(8, min(40, int(self.grid_density * aspect)))
        ny = int(self.grid_density)

        xs = np.linspace(wx_min, wx_max, nx)
        ys = np.linspace(wy_min, wy_max, ny)

        cache_key = system.uid
        cache_ok = (cache_key in self.field_cache and
                    self.field_cache_scale == self.scale and
                    np.allclose(self.field_cache_offset, self.offset) and
                    self.field_cache_t == self.t)

        if cache_ok:
            grid = self.field_cache[cache_key]
        else:
            grid = []
            for xi in xs:
                for yi in ys:
                    vx, vy = system.eval_dxdy(xi, yi, self.t)
                    grid.append((xi, yi, vx, vy))
            self.field_cache[cache_key] = grid
            self.field_cache_scale = self.scale
            self.field_cache_offset = self.offset.copy()
            self.field_cache_t = self.t

        # Use system color for arrows
        arrow_color = QColor(system.color)
        arrow_color.setAlpha(160)

        for xi, yi, vx, vy in grid:
            sx, sy = self.world_to_screen(xi, yi)
            vec = np.array([vx, vy], dtype=float)
            norm = np.linalg.norm(vec)
            if norm == 0:
                continue

            arrow_len = 0.8 * min(self.scale, 20)
            dirx = (vec[0] / norm)
            diry = -(vec[1] / norm)

            dx = dirx * arrow_len
            dy = diry * arrow_len
            x2 = sx + dx
            y2 = sy + dy

            pen = QPen(arrow_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(QPointF(sx, sy), QPointF(x2, y2))

            ah = 4 + self.scale * 0.01
            head_angle = math.pi / 6
            theta = math.atan2(dy, dx)

            backx = -math.cos(theta)
            backy = -math.sin(theta)

            c = math.cos(head_angle)
            s = math.sin(head_angle)
            leftx = backx * c - backy * s
            lefty = backx * s + backy * c
            rightx = backx * c + backy * s
            righty = -backx * s + backy * c

            p1 = QPointF(x2 + ah * leftx, y2 + ah * lefty)
            p2 = QPointF(x2 + ah * rightx, y2 + ah * righty)
            painter.drawLine(QPointF(x2, y2), p1)
            painter.drawLine(QPointF(x2, y2), p2)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.placing_mode:
                sx, sy = ev.position().x(), ev.position().y()
                wx, wy = self.screen_to_world(sx, sy)

                # Ensure we have an active system - fallback to first system if none selected
                if self.active_system_uid is None and self.systems:
                    self.active_system_uid = self.systems[0].uid

                # Get active system color
                active_sys = self.get_system(self.active_system_uid)
                particle_color = active_sys.color if active_sys else QColor('#ffffff')
                system_id = active_sys.uid if active_sys else (self.systems[0].uid if self.systems else None)

                newp = Particle(wx, wy, color=particle_color, system_id=system_id)
                newp.reset_history()
                self.particles.append(newp)

                self.x_overlay.add_system(newp.uid, newp.color, newp.name)
                self.y_overlay.add_system(newp.uid, newp.color, newp.name)

                self.placing_mode = False
                self.update()
            else:
                self.pan_last = np.array([ev.position().x(), ev.position().y()])
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        self.mouse_pos = (ev.position().x(), ev.position().y())
        if getattr(self, 'pan_last', None) is not None and not self.placing_mode:
            cur = np.array([ev.position().x(), ev.position().y()])
            delta = cur - self.pan_last
            self.offset -= delta / self.scale * np.array([1.0, -1.0])
            self.pan_last = cur
            self.field_cache = {}
            self.update()
        else:
            self.update()
        super().mouseMoveEvent(ev)

    def enterEvent(self, ev):
        self.update()
        super().enterEvent(ev)

    def mouseReleaseEvent(self, ev):
        self.pan_last = None
        super().mouseReleaseEvent(ev)

    def wheelEvent(self, ev):
        degrees = ev.angleDelta().y() / 8
        steps = degrees / 15
        factor = 1.0 + steps * 0.1
        if factor <= 0:
            return
        sx = ev.position().x()
        sy = ev.position().y()
        wx, wy = self.screen_to_world(sx, sy)
        self.scale *= factor
        self.offset[0] = wx - (sx - self.width() / 2) / self.scale
        self.offset[1] = wy + (sy - self.height() / 2) / self.scale
        self.field_cache = {}
        self.update()
        super().wheelEvent(ev)

    def on_frame(self):
        now = time.time()
        elapsed = now - self.last_frame_time
        self.last_frame_time = now

        if self.simulation_running:
            sim_elapsed = elapsed * float(self.time_scale)
            steps = max(1, int(sim_elapsed / self.dt))
            h = sim_elapsed / steps

            for _ in range(steps):
                self.t += h
                self.field_cache = {}

                # Step stochastic gates once per integrator substep
                for g in self.gates.values():
                    try:
                        g.step(h)
                    except Exception:
                        pass

                # Update step functions with current time
                for sf in self.step_functions.values():
                    try:
                        sf.update_time(self.t)
                    except Exception:
                        pass

                # Update particles and push samples per particle
                for p in self.particles:
                    if p.running and not p.hiden:
                        system = self.get_system(p.system_id)
                        if system is None:
                            continue

                        # RK4 integration
                        # RK4 integration
                        def make_state_provider(current_x, current_y, current_t):
                            def state_provider(var, query_t, default):
                                if abs(query_t - current_t) < 1e-9:
                                    return current_x if var == 'x' else current_y
                                return p.get_state_at(var, query_t, default)

                            return state_provider

                        k1x, k1y = system.eval_dxdy(p.x, p.y, self.t, h,
                                                    state_provider=make_state_provider(p.x, p.y, self.t),
                                                    custom_vars=p.custom_vars)

                        x2 = p.x + 0.5 * h * k1x
                        y2 = p.y + 0.5 * h * k1y
                        t2 = self.t + 0.5 * h
                        k2x, k2y = system.eval_dxdy(x2, y2, t2, h,
                                                    state_provider=make_state_provider(x2, y2, t2),
                                                    custom_vars=p.custom_vars)

                        x3 = p.x + 0.5 * h * k2x
                        y3 = p.y + 0.5 * h * k2y
                        t3 = self.t + 0.5 * h
                        k3x, k3y = system.eval_dxdy(x3, y3, t3, h,
                                                    state_provider=make_state_provider(x3, y3, t3),
                                                    custom_vars=p.custom_vars)

                        x4 = p.x + h * k3x
                        y4 = p.y + h * k3y
                        t4 = self.t + h
                        k4x, k4y = system.eval_dxdy(x4, y4, t4, h,
                                                    state_provider=make_state_provider(x4, y4, t4),
                                                    custom_vars=p.custom_vars)

                        vx = (k1x + 2 * k2x + 2 * k3x + k4x) / 6.0
                        vy = (k1y + 2 * k2y + 2 * k3y + k4y) / 6.0

                        p.step(vx, vy, h, self.t)

                        # Push samples to particle trace (not system trace)
                        if system.show_overlay:
                            self.x_overlay.push_sample(p.uid, self.t, p.x)
                            self.y_overlay.push_sample(p.uid, self.t, p.y)

        # Update custom traces (once per frame, using first running particle per system)
        for system in self.systems:
            if system.show_overlay:
                sys_particles = [p for p in self.particles if p.system_id == system.uid]
                if sys_particles:
                    p = next((pp for pp in sys_particles if pp.running), sys_particles[0])
                    if p.history:
                        t_cur, x_cur, y_cur = p.history[-1][0], p.history[-1][1], p.history[-1][2]

                        def provider(var, qt, default):
                            return float(x_cur) if var == 'x' else float(y_cur) if var == 'y' else float(default)

                        if self.x_overlay.isVisible():
                            self.x_overlay.update_custom_traces(x_cur, y_cur, t_cur, state_provider=provider)
                        if self.y_overlay.isVisible():
                            self.y_overlay.update_custom_traces(x_cur, y_cur, t_cur, state_provider=provider)

        # Update overlay time reference so hidden traces scroll off
        self.x_overlay.current_t = self.t
        self.y_overlay.current_t = self.t

        # In PhaseCanvas.on_frame(), after updating particles:
        if hasattr(self, 'calc_overlay'):
            self.calc_overlay.update_result()

        self.update()


# --------------------- System Editor Widget ---------------------

class SystemEditor(QGroupBox):
    """Widget to edit a single dynamical system's properties."""

    def __init__(self, system: DynamicalSystem, parent=None):
        super().__init__(parent)
        self.system = system
        self.setTitle(system.name)
        self.setCheckable(False)

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # Name and color row
        name_row = QHBoxLayout()
        self.name_input = QLineEdit(system.name)
        self.name_input.setPlaceholderText('System name')
        self.name_input.textChanged.connect(self._on_name_changed)

        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(24, 24)
        self._update_color_btn()
        self.color_btn.clicked.connect(self._on_color_click)

        name_row.addWidget(QLabel('Name:'))
        name_row.addWidget(self.name_input, 1)
        name_row.addWidget(self.color_btn)
        layout.addLayout(name_row)

        # dx/dt
        dx_row = QHBoxLayout()
        dx_row.addWidget(QLabel('dx/dt ='))
        self.dx_input = QLineEdit(system.dx_expr)
        self.dx_input.textChanged.connect(self._on_equations_changed)
        dx_row.addWidget(self.dx_input, 1)
        layout.addLayout(dx_row)

        # dy/dt
        dy_row = QHBoxLayout()
        dy_row.addWidget(QLabel('dy/dt ='))
        self.dy_input = QLineEdit(system.dy_expr)
        self.dy_input.textChanged.connect(self._on_equations_changed)
        dy_row.addWidget(self.dy_input, 1)
        layout.addLayout(dy_row)

        # Visibility checkboxes
        vis_row = QHBoxLayout()
        self.show_arrows_cb = QCheckBox('Arrows')
        self.show_arrows_cb.setChecked(system.show_arrows)
        self.show_arrows_cb.toggled.connect(self._on_show_arrows)

        self.show_particles_cb = QCheckBox('Particles')
        self.show_particles_cb.setChecked(system.show_particles)
        self.show_particles_cb.toggled.connect(self._on_show_particles)

        self.show_overlay_cb = QCheckBox('Graphs')
        self.show_overlay_cb.setChecked(system.show_overlay)
        self.show_overlay_cb.toggled.connect(self._on_show_overlay)

        vis_row.addWidget(self.show_arrows_cb)
        vis_row.addWidget(self.show_particles_cb)
        vis_row.addWidget(self.show_overlay_cb)
        vis_row.addStretch()
        layout.addLayout(vis_row)

        self.setLayout(layout)

        # Callbacks
        self.on_change = None
        self.on_color_change = None
        self.on_remove = None

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(f'background-color: {self.system.color.name()}; border: 1px solid #888;')

    def _on_name_changed(self, text):
        self.system.name = text
        self.setTitle(text)
        if self.on_change:
            self.on_change(self.system)

    def _on_equations_changed(self):
        self.system.dx_expr = self.dx_input.text()
        self.system.dy_expr = self.dy_input.text()
        self.system.compile_equations()
        if self.on_change:
            self.on_change(self.system)

    def _on_color_click(self):
        col = QColorDialog.getColor(self.system.color, self)
        if col.isValid():
            self.system.color = col
            self._update_color_btn()
            if self.on_color_change:
                self.on_color_change(self.system)

    def _on_show_arrows(self, checked):
        self.system.show_arrows = checked
        if self.on_change:
            self.on_change(self.system)

    def _on_show_particles(self, checked):
        self.system.show_particles = checked
        if self.on_change:
            self.on_change(self.system)

    def _on_show_overlay(self, checked):
        self.system.show_overlay = checked
        if self.on_change:
            self.on_change(self.system)

# --------------------- Main Tab Widget ---------------------

class PhaseTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = PhaseCanvas()

        self.selected_particle_uid = None
        self.system_editors = {}  # uid -> SystemEditor widget

        # Gates created from 'gate' definitions (name -> TwoStateGate)
        self.gates: dict[str, TwoStateGate] = {}

        # Model definitions: list of rows {type, name, expr/widget}
        self.def_rows = []

        # Model environment (shared across all systems)
        self.model_env = {}

        # Time readout + speed
        self.time_label = QLabel('t = 0.000 s')
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.0, 1000.0)
        self.speed_spin.setDecimals(3)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.valueChanged.connect(self.on_speed_changed)

        # Add Variable button
        self.add_var_btn = QPushButton("+ Variable")
        self.add_var_btn.setToolTip("Add a custom variable to all particles")
        self.add_var_btn.clicked.connect(self._add_particle_variable)

        # Place/run controls
        place_btn = QPushButton('Place point')
        place_btn.setCheckable(True)
        place_btn.toggled.connect(self.toggle_placing)

        run_btn = QPushButton('Run')
        run_btn.setCheckable(True)
        run_btn.toggled.connect(self.toggle_run)

        pause_btn = QPushButton('Pause')
        pause_btn.clicked.connect(self.pause_sim)

        reset_btn = QPushButton('Reset')
        reset_btn.clicked.connect(self.reset_simulation)

        # System selector for placing particles
        self.system_combo = QComboBox()
        self.system_combo.currentIndexChanged.connect(self._on_system_combo_changed)

        # Axis name + unit
        self.x_label_input = QLineEdit('x')
        self.y_label_input = QLineEdit('y')
        self.x_unit_input = QLineEdit('')
        self.y_unit_input = QLineEdit('')
        self.x_unit_input.setPlaceholderText('unit')
        self.y_unit_input.setPlaceholderText('unit')

        self.x_label_input.textChanged.connect(self.apply_axis_labels)
        self.y_label_input.textChanged.connect(self.apply_axis_labels)
        self.x_unit_input.textChanged.connect(self.apply_axis_labels)
        self.y_unit_input.textChanged.connect(self.apply_axis_labels)

        show_values_cb = QCheckBox('Show values')
        show_values_cb.setChecked(True)
        show_values_cb.toggled.connect(self.toggle_show_values)

        dark_btn = QPushButton('Toggle Dark')
        dark_btn.setCheckable(True)
        dark_btn.setChecked(True)
        dark_btn.toggled.connect(self.toggle_dark)

        # Top layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(place_btn)
        top_layout.addWidget(QLabel('to:'))
        top_layout.addWidget(self.system_combo)
        top_layout.addWidget(run_btn)
        top_layout.addWidget(pause_btn)
        top_layout.addWidget(reset_btn)
        top_layout.addWidget(show_values_cb)
        top_layout.addStretch(1)
        top_layout.addWidget(QLabel('X:'))
        top_layout.addWidget(self.x_label_input)
        top_layout.addWidget(QLabel('['))
        top_layout.addWidget(self.x_unit_input)
        top_layout.addWidget(QLabel(']'))
        top_layout.addWidget(QLabel('Y:'))
        top_layout.addWidget(self.y_label_input)
        top_layout.addWidget(QLabel('['))
        top_layout.addWidget(self.y_unit_input)
        top_layout.addWidget(QLabel(']'))
        top_layout.addWidget(dark_btn)

        # Particles list
        '''
        self.side_list = QListWidget()
        self.side_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.side_list.currentItemChanged.connect(self.on_particle_selection_changed)
        self.side_list.viewport().installEventFilter(self)  # Add this line
        '''
        self.side_list = QTreeWidget()
        self.side_list.setHeaderHidden(True)
        self.side_list.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.side_list.itemSelectionChanged.connect(self.on_particle_selection_changed)

        add_color_btn = QPushButton('Color')
        add_color_btn.clicked.connect(self.change_selected_color)
        remove_btn = QPushButton('Remove Particle')
        remove_btn.clicked.connect(self.remove_selected_particle)

        fade_lbl = QLabel('Trail (s):')
        self.fade_spin = QSpinBox()
        self.fade_spin.setRange(0, 60)
        self.fade_spin.setValue(5)
        self.fade_spin.valueChanged.connect(self.change_fade_time)

        # Save / load
        save_btn = QPushButton('Save')
        save_btn.clicked.connect(self.save_to_file)
        load_btn = QPushButton('Load')
        load_btn.clicked.connect(self.load_from_file)

        # Systems panel
        systems_panel = QWidget()
        systems_layout = QVBoxLayout()
        systems_layout.setContentsMargins(0, 0, 0, 0)
        systems_layout.setSpacing(4)
        systems_panel.setLayout(systems_layout)

        systems_layout.addWidget(QLabel('Dynamical Systems'))

        self.systems_container = QWidget()
        self.systems_vlayout = QVBoxLayout()
        self.systems_vlayout.setContentsMargins(0, 0, 0, 0)
        self.systems_vlayout.setSpacing(4)
        self.systems_container.setLayout(self.systems_vlayout)

        systems_scroll = QScrollArea()
        systems_scroll.setWidgetResizable(True)
        systems_scroll.setWidget(self.systems_container)
        systems_scroll.setMinimumHeight(150)
        systems_layout.addWidget(systems_scroll, 1)

        sys_btn_row = QHBoxLayout()
        add_sys_btn = QPushButton('+ Add System')
        add_sys_btn.clicked.connect(self.add_system)
        remove_sys_btn = QPushButton('- Remove Selected')
        remove_sys_btn.clicked.connect(self.remove_selected_system)
        sys_btn_row.addWidget(add_sys_btn)
        sys_btn_row.addWidget(remove_sys_btn)
        systems_layout.addLayout(sys_btn_row)

        # Definitions panel (constants, functions, gates)
        defs_panel = QWidget()
        defs_layout = QVBoxLayout()
        defs_layout.setContentsMargins(0, 0, 0, 0)
        defs_layout.setSpacing(4)
        defs_panel.setLayout(defs_layout)

        defs_layout.addWidget(QLabel('Definitions (const / func / gate)'))

        self.defs_container = QWidget()
        self.defs_vlayout = QVBoxLayout()
        self.defs_vlayout.setContentsMargins(0, 0, 0, 0)
        self.defs_vlayout.setSpacing(4)
        self.defs_container.setLayout(self.defs_vlayout)

        defs_scroll = QScrollArea()
        defs_scroll.setWidgetResizable(True)
        defs_scroll.setWidget(self.defs_container)
        defs_scroll.setMinimumHeight(120)
        defs_layout.addWidget(defs_scroll, 1)

        add_def_btn = QPushButton('+ Add Definition')
        add_def_btn.clicked.connect(lambda _checked=False: self.add_definition_row())
        defs_layout.addWidget(add_def_btn)

        # Right side layout
        side_layout = QVBoxLayout()
        side_layout.addWidget(systems_panel, 2)
        side_layout.addWidget(defs_panel, 2)

        # Time row
        time_row = QHBoxLayout()
        time_row.addWidget(self.time_label)
        time_row.addStretch(1)
        time_row.addWidget(QLabel('Speed ×'))
        time_row.addWidget(self.speed_spin)
        side_layout.addLayout(time_row)

        side_layout.addWidget(QLabel('Particles'))
        side_layout.addWidget(self.add_var_btn)
        side_layout.addWidget(self.side_list, 2)

        particle_btn_row = QHBoxLayout()
        particle_btn_row.addWidget(add_color_btn)
        particle_btn_row.addWidget(remove_btn)
        side_layout.addLayout(particle_btn_row)

        side_layout.addWidget(fade_lbl)
        side_layout.addWidget(self.fade_spin)
        side_layout.addStretch()
        side_layout.addWidget(save_btn)
        side_layout.addWidget(load_btn)

        side_widget = QWidget()
        side_widget.setLayout(side_layout)
        self.side_widget = side_widget

        splitter = QSplitter()
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.canvas)
        main_widget.setLayout(main_layout)

        splitter.addWidget(main_widget)
        splitter.addWidget(side_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        # Timers
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.sync_ui)
        self.ui_timer.start(120)

        # Store refs
        self.place_btn = place_btn
        self.run_btn = run_btn

        # Initialize
        self.apply_axis_labels()

        # Add default system
        self.add_system()

        # Add example definition rows
        self.add_definition_row(default_kind='const')
        self.add_definition_row(default_kind='func')
        self.rebuild_model_env_and_recompile()

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and event.type() == event.Type.MouseButtonPress:
            obj.click()
            return True
        return super().eventFilter(obj, event)

    def refresh_particle_list(self):
        self.side_list.clear()
        for p in self.canvas.particles:
            # Parent item (selectable) - particle header
            system = self.canvas.get_system(p.system_id)
            sys_name = system.name if system else '?'
            text = f'{p.name} [{sys_name}] ({p.x:.2f}, {p.y:.2f})'
            parent_item = QTreeWidgetItem([text])
            parent_item.setData(0, Qt.ItemDataRole.UserRole, p.uid)
            self.side_list.addTopLevelItem(parent_item)

            # Variable rows as children (non-selectable)
            for var_name in p.custom_vars:
                child_item = QTreeWidgetItem()
                child_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Non-selectable
                child_item.setData(0, Qt.ItemDataRole.UserRole, ('var', p.uid, var_name))
                parent_item.addChild(child_item)

                # Add widget to child
                row_widget = self._create_variable_row_widget(p, var_name)
                self.side_list.setItemWidget(child_item, 0, row_widget)

            parent_item.setExpanded(True)

    def add_definition_row(self, default_kind: str = 'const', *_args, **_kwargs):
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_widget.setLayout(row_layout)

        kind_input = QLineEdit(default_kind)
        kind_input.setFixedWidth(44)
        kind_input.setToolTip("Type: 'const', 'func', or 'gate' (kon,koff[,initial])")

        name_input = QLineEdit('a' if default_kind == 'const' else 'alpha')
        name_input.setPlaceholderText('name')
        name_input.setFixedWidth(90)

        expr_input = QLineEdit('1.0' if default_kind == 'const' else 'sin(t)')
        expr_input.setPlaceholderText('expr (use t)')

        del_btn = QPushButton('×')
        del_btn.setFixedWidth(26)

        row_layout.addWidget(kind_input)
        row_layout.addWidget(name_input)
        row_layout.addWidget(expr_input, 1)
        row_layout.addWidget(del_btn)

        self.defs_vlayout.addWidget(row_widget)

        row = {
            'widget': row_widget,
            'kind': kind_input,
            'name': name_input,
            'expr': expr_input,
        }
        self.def_rows.append(row)

        def on_change(_=None):
            self.rebuild_model_env_and_recompile()

        kind_input.textChanged.connect(on_change)
        name_input.textChanged.connect(on_change)
        expr_input.textChanged.connect(on_change)
        del_btn.clicked.connect(lambda: self.remove_definition_row(row))

    def remove_definition_row(self, row):
        if row in self.def_rows:
            self.def_rows.remove(row)
        w = row.get('widget')
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        self.rebuild_model_env_and_recompile()

    def rebuild_model_env_and_recompile(self):
        """Build env from UI definitions and recompile all systems.

        Supported kinds:
        - const: constant numeric value (expression evaluated at t=0)
        - func: function of t (expression evaluated as f(t))
        - gate: two-state stochastic variable; expr is 'kon, koff[, initial]' (numbers or expressions)
        - step: periodic step function; expr is 'dt0, dt1' (time at 0, time at 1)
        - smoothstep: smooth periodic step function; expr is 'dt0, dt1[, k_rise, k_fall]'
        """
        env: dict = {}
        gates: dict[str, TwoStateGate] = {}
        step_functions: dict[str, StepFunction | SmoothStepFunction] = {}

        for row in self.def_rows:
            kind = (row['kind'].text() or '').strip().lower()
            name = (row['name'].text() or '').strip()
            expr = (row['expr'].text() or '').strip()

            if not name or not expr:
                continue

            try:
                name = _validate_identifier(name)
            except Exception:
                continue

            try:
                if kind in ('gate', 'g'):
                    # gate: expr is "kon, koff" or "kon, koff, initial".
                    parts = [p.strip() for p in expr.split(',') if p.strip()]
                    if len(parts) < 2:
                        continue

                    kon_fn = _compile_definition_expr(parts[0], extra_names=env)
                    koff_fn = _compile_definition_expr(parts[1], extra_names=env)
                    init_val = 0
                    if len(parts) >= 3:
                        init_fn = _compile_definition_expr(parts[2], extra_names=env)
                        init_val = int(round(float(init_fn(0.0))))

                    g = TwoStateGate(float(kon_fn(0.0)), float(koff_fn(0.0)), initial=init_val, name=name)
                    gates[name] = g
                    env[name] = g

                elif kind in ('smoothstep', 'ss', 'smooth'):
                    # smoothstep: expr is "dt0, dt1" or "dt0, dt1, k_rise, k_fall"
                    parts = [p.strip() for p in expr.split(',') if p.strip()]
                    if len(parts) < 2:
                        continue

                    dt0_fn = _compile_definition_expr(parts[0], extra_names=env)
                    dt1_fn = _compile_definition_expr(parts[1], extra_names=env)

                    k_rise = 10.0
                    k_fall = 10.0
                    if len(parts) >= 3:
                        k_rise_fn = _compile_definition_expr(parts[2], extra_names=env)
                        k_rise = float(k_rise_fn(0.0))
                    if len(parts) >= 4:
                        k_fall_fn = _compile_definition_expr(parts[3], extra_names=env)
                        k_fall = float(k_fall_fn(0.0))

                    sf = SmoothStepFunction(float(dt0_fn(0.0)), float(dt1_fn(0.0)), k_rise, k_fall, name=name)
                    step_functions[name] = sf
                    env[name] = sf

                elif kind in ('step', 's'):
                    # step: expr is "dt0, dt1" (time spent at 0, time spent at 1)
                    parts = [p.strip() for p in expr.split(',') if p.strip()]
                    if len(parts) < 2:
                        continue

                    dt0_fn = _compile_definition_expr(parts[0], extra_names=env)
                    dt1_fn = _compile_definition_expr(parts[1], extra_names=env)

                    sf = StepFunction(float(dt0_fn(0.0)), float(dt1_fn(0.0)), name=name)
                    step_functions[name] = sf
                    env[name] = sf

                elif kind in ('const', 'c'):
                    gt = _compile_definition_expr(expr, extra_names=env)
                    env[name] = float(gt(0.0))
                else:
                    # function of t
                    gt = _compile_definition_expr(expr, extra_names=env)
                    env[name] = gt
            except Exception:
                continue

        try:
            self.gates = gates
            self.step_functions = step_functions
            self.model_env = env

            # Pass gates and step functions to canvas so they can be updated during simulation
            self.canvas.gates = gates
            self.canvas.step_functions = step_functions

            # Pass model_env to canvas so overlays can access it
            self.canvas.model_env = env

            # Update all systems with new model environment
            for system in self.canvas.systems:
                system.model_env = env
                system.compile_equations()

            # Recompile custom traces in overlays with the new environment
            self.canvas.x_overlay.recompile_custom_traces()
            self.canvas.y_overlay.recompile_custom_traces()

            self.canvas.field_cache = {}
        except Exception:
            pass

        self.model_env = env
        self.gates = gates
        self.canvas.gates = gates
        self.canvas.step_functions = step_functions

        # Recompile all systems with the updated environment
        for system in self.canvas.systems:
            system.model_env = self.model_env
            system.compile_equations()

        # Recompile custom traces in overlays
        self.canvas.x_overlay.recompile_custom_traces()
        self.canvas.y_overlay.recompile_custom_traces()

        self.canvas.field_cache = {}
        self.canvas.update()

    def add_system(self):
        idx = len(self.canvas.systems) + 1
        color = SYSTEM_COLORS[(idx - 1) % len(SYSTEM_COLORS)]
        system = DynamicalSystem(
            name=f'System {idx}',
            dx_expr='y',
            dy_expr='-x',
            color=color
        )

        # Set the model environment before compiling
        system.model_env = self.model_env
        system.compile_equations()

        self.canvas.add_system(system)

        # Create editor widget
        editor = SystemEditor(system)
        editor.on_change = self._on_system_changed
        editor.on_color_change = self._on_system_color_changed
        self.system_editors[system.uid] = editor
        self.systems_vlayout.addWidget(editor)

        self._update_system_combo()
        self.canvas.field_cache = {}
        self.canvas.update()

    def remove_selected_system(self):
        if len(self.canvas.systems) <= 1:
            return  # Keep at least one system

        # Get current system from combo
        idx = self.system_combo.currentIndex()
        if idx < 0 or idx >= len(self.canvas.systems):
            return

        system = self.canvas.systems[idx]

        # Remove editor widget
        if system.uid in self.system_editors:
            editor = self.system_editors.pop(system.uid)
            editor.setParent(None)
            editor.deleteLater()

        self.canvas.remove_system(system.uid)
        self._update_system_combo()
        self.sync_side_list()
        self.canvas.update()

    def _update_system_combo(self):
        self.system_combo.blockSignals(True)
        self.system_combo.clear()
        for sys in self.canvas.systems:
            self.system_combo.addItem(sys.name, sys.uid)

        # Select the active system
        for i, sys in enumerate(self.canvas.systems):
            if sys.uid == self.canvas.active_system_uid:
                self.system_combo.setCurrentIndex(i)
                break
        self.system_combo.blockSignals(False)

    def _on_system_combo_changed(self, idx):
        if idx >= 0:
            uid = self.system_combo.currentData()
            if uid is not None:
                self.canvas.active_system_uid = uid

    def _on_system_changed(self, system):
        self.canvas.field_cache = {}
        self._update_system_combo()

        # Update overlay labels
        self.canvas.x_overlay.update_system_label(system.uid, system.name)
        self.canvas.y_overlay.update_system_label(system.uid, system.name)

        self.canvas.update()

    def _on_system_color_changed(self, system):
        self.canvas.x_overlay.update_system_color(system.uid, system.color)
        self.canvas.y_overlay.update_system_color(system.uid, system.color)

        # Update particle colors for this system
        for p in self.canvas.particles:
            if p.system_id == system.uid:
                p.color = QColor(system.color)

        self.sync_side_list()
        self.canvas.update()

    def on_speed_changed(self, v: float):
        self.canvas.time_scale = float(v)

    def toggle_placing(self, v):
        self.canvas.placing_mode = v

    def toggle_run(self, v):
        self.canvas.simulation_running = v
        for p in self.canvas.particles:
            p.running = v

    def pause_sim(self):
        self.canvas.simulation_running = False
        self.run_btn.setChecked(False)

    def toggle_show_values(self, v):
        self.canvas.show_values = v

    '''
    def on_particle_selection_changed(self, current, previous):
        if current is None:
            self.selected_particle_uid = None
            self.canvas.active_particle_uid = None
            return
        self.selected_particle_uid = current.data(Qt.ItemDataRole.UserRole)
        self.canvas.active_particle_uid = self.selected_particle_uid
    '''

    def on_particle_selection_changed(self):
        items = self.side_list.selectedItems()
        if items:
            item = items[0]
            # Only top-level items (particles) have uid data
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:  # It's a particle item
                self.selected_particle_uid = data
                self.canvas.active_particle_uid = data
            else:
                # Child item selected - select the parent instead
                parent = item.parent()
                if parent:
                    self.side_list.setCurrentItem(parent)
        else:
            self.selected_particle_uid = None
            self.canvas.active_particle_uid = None

    def _get_selected_particle_index(self):
        uid = self.selected_particle_uid
        if not uid:
            return None
        for i, p in enumerate(self.canvas.particles):
            if getattr(p, 'uid', None) == uid:
                return i
        return None

    def change_selected_color(self):
        idx = self._get_selected_particle_index()
        if idx is None:
            return
        p = self.canvas.particles[idx]
        col = QColorDialog.getColor(p.color, self)
        if col.isValid():
            p.color = col
            self.sync_side_list(preserve_selection=True)

            self.canvas.x_overlay.update_system_color(p.uid, p.color)
            self.canvas.y_overlay.update_system_color(p.uid, p.color)

            self.canvas.update()

    def remove_selected_particle(self):
        idx = self._get_selected_particle_index()
        if idx is None:
            return
        p = self.canvas.particles[idx]
        self.canvas.x_overlay.remove_system(p.uid)
        self.canvas.y_overlay.remove_system(p.uid)
        del self.canvas.particles[idx]
        self.selected_particle_uid = None
        self.sync_side_list(preserve_selection=False)
        self.canvas.update()

    def reset_simulation(self):
        self.canvas.simulation_running = False
        self.run_btn.setChecked(False)

        self.canvas.t = 0.0
        self.canvas.last_frame_time = time.time()

        for p in self.canvas.particles:
            p.reset()
            p.max_history_time = float(self.fade_spin.value())

        # Clear overlay samples
        self.canvas.x_overlay.clear()
        self.canvas.y_overlay.clear()

        self.sync_side_list()
        self.canvas.update()

    def change_fade_time(self, v):
        for p in self.canvas.particles:
            p.max_history_time = float(v)

    def toggle_dark(self, v):
        self.canvas.dark_mode = v

    def sync_ui(self):
        self.time_label.setText(f't = {self.canvas.t:.3f} s')
        self.sync_side_list(preserve_selection=True)

    '''
    def sync_side_list(self, preserve_selection: bool = True):
        prev_uid = self.selected_particle_uid if preserve_selection else None

        self.side_list.blockSignals(True)
        self.side_list.clear()

        selected_row = None

        for i, p in enumerate(self.canvas.particles):
            system = self.canvas.get_system(p.system_id)
            sys_name = system.name if system else "?"

            # 1) Item = container only (no visible text)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p.uid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            # 2) Row widget = actual visuals (label + button)
            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

            lay = QHBoxLayout(row)
            lay.setContentsMargins(6, 2, 6, 2)
            lay.setSpacing(8)

            lbl = QLabel(f"[{sys_name}] {p.name}: ({p.x:.2f}, {p.y:.2f})")
            lbl.setStyleSheet(f"color: {p.color.name()};")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

            btn = QPushButton("Show" if p.hiden else "Hide")
            btn.setProperty("particle_uid", p.uid)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda _=False, uid=p.uid: self._hide_particle(uid))
            btn.raise_()
            btn.installEventFilter(self)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

            lay.addWidget(lbl, 1)
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)

            # Add + size
            self.side_list.addItem(item)
            item.setSizeHint(row.sizeHint())
            self.side_list.setItemWidget(item, row)

            if prev_uid and p.uid == prev_uid:
                selected_row = i

        self.side_list.blockSignals(False)

        if selected_row is not None:
            self.side_list.setCurrentRow(selected_row)
            self.selected_particle_uid = prev_uid
        else:
            self.selected_particle_uid = None
    '''
    '''
    def sync_side_list(self, preserve_selection: bool = True):
        prev_uid = self.selected_particle_uid if preserve_selection else None

        self.side_list.blockSignals(True)
        self.side_list.clear()

        selected_row = None

        # Get all variable names across all particles
        all_var_names = set()
        for p in self.canvas.particles:
            all_var_names.update(p.custom_vars.keys())
        var_names = sorted(all_var_names)

        row_idx = 0
        for i, p in enumerate(self.canvas.particles):
            # Ensure particle has all variables
            for vn in var_names:
                if vn not in p.custom_vars:
                    p.custom_vars[vn] = 0.0

            system = self.canvas.get_system(p.system_id)
            sys_name = system.name if system else "?"

            # Main particle row
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p.uid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

            lay = QHBoxLayout(row)
            lay.setContentsMargins(6, 2, 6, 2)
            lay.setSpacing(8)

            lbl = QLabel(f"[{sys_name}] {p.name}: ({p.x:.2f}, {p.y:.2f})")
            lbl.setStyleSheet(f"color: {p.color.name()};")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

            btn = QPushButton("Show" if p.hiden else "Hide")
            btn.setProperty("particle_uid", p.uid)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda _=False, uid=p.uid: self._hide_particle(uid))
            btn.raise_()
            btn.installEventFilter(self)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

            lay.addWidget(lbl, 1)
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)

            self.side_list.addItem(item)
            item.setSizeHint(row.sizeHint())
            self.side_list.setItemWidget(item, row)

            if prev_uid and p.uid == prev_uid:
                selected_row = row_idx
            row_idx += 1

            # Variable rows for this particle
            for var_name in var_names:
                var_item = QListWidgetItem()
                var_item.setData(Qt.ItemDataRole.UserRole, ('var', p.uid, var_name))
                # Fully disable selection and interaction for variable rows
                var_item.setFlags(Qt.ItemFlag.NoItemFlags)
                var_widget = self._create_variable_row_widget(p, var_name)
                self.side_list.addItem(var_item)
                var_item.setSizeHint(var_widget.sizeHint())
                self.side_list.setItemWidget(var_item, var_widget)
                row_idx += 1

        self.side_list.blockSignals(False)

        if selected_row is not None:
            self.side_list.setCurrentRow(selected_row)
            self.selected_particle_uid = prev_uid
        else:
            self.selected_particle_uid = None
    '''

    def sync_side_list(self, preserve_selection: bool = True):
        prev_uid = self.selected_particle_uid if preserve_selection else None

        # Check if we actually need to rebuild
        current_items = self.side_list.topLevelItemCount()
        if current_items == len(self.canvas.particles) and preserve_selection:
            # Just update text, don't rebuild
            for i in range(current_items):
                item = self.side_list.topLevelItem(i)
                if i < len(self.canvas.particles):
                    p = self.canvas.particles[i]
                    system = self.canvas.get_system(p.system_id)
                    sys_name = system.name if system else '?'
                    text = f'{p.name} [{sys_name}] ({p.x:.2f}, {p.y:.2f})'
                    item.setText(0, text)
            return

        # Full rebuild needed
        self.side_list.blockSignals(True)
        self.side_list.clear()

        selected_item = None

        for p in self.canvas.particles:
            system = self.canvas.get_system(p.system_id)
            sys_name = system.name if system else '?'
            text = f'{p.name} [{sys_name}] ({p.x:.2f}, {p.y:.2f})'
            parent_item = QTreeWidgetItem([text])
            parent_item.setData(0, Qt.ItemDataRole.UserRole, p.uid)
            self.side_list.addTopLevelItem(parent_item)

            if p.uid == prev_uid:
                selected_item = parent_item

            # Hide button - use default argument to capture uid by value
            hide_child = QTreeWidgetItem()
            hide_child.setFlags(Qt.ItemFlag.NoItemFlags)
            parent_item.addChild(hide_child)

            hide_btn = QPushButton('Show' if p.hiden else 'Hide')
            hide_btn.setFixedHeight(20)
            uid_copy = p.uid  # Capture by value
            hide_btn.clicked.connect(lambda checked=False, uid=uid_copy: self._hide_particle(uid))
            self.side_list.setItemWidget(hide_child, 0, hide_btn)

            # Variable rows
            for var_name in sorted(p.custom_vars.keys()):
                child_item = QTreeWidgetItem()
                child_item.setFlags(Qt.ItemFlag.NoItemFlags)
                parent_item.addChild(child_item)
                row_widget = self._create_variable_row_widget(p, var_name)
                self.side_list.setItemWidget(child_item, 0, row_widget)

            parent_item.setExpanded(True)

        self.side_list.blockSignals(False)

        if selected_item is not None:
            self.side_list.setCurrentItem(selected_item)
        else:
            self.selected_particle_uid = None

    def _create_variable_row_widget(self, p: Particle, var_name: str):
        """Create a widget for a particle's custom variable."""
        row = QWidget()
        row.setStyleSheet("background: transparent; margin-left: 20px;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(20, 2, 4, 2)
        layout.setSpacing(4)

        # Variable name (editable, syncs across all particles)
        name_edit = QLineEdit(var_name)
        name_edit.setFixedWidth(50)
        name_edit.setToolTip("Variable name (shared across all particles)")

        def on_name_change():
            new_name = name_edit.text().strip()
            if new_name and new_name != var_name:
                self._rename_particle_variable(var_name, new_name)

        name_edit.editingFinished.connect(on_name_change)
        layout.addWidget(name_edit)

        # Equals sign
        eq_label = QLabel("=")
        layout.addWidget(eq_label)

        # Value (text input, specific to this particle)
        current_val = p.custom_vars.get(var_name, 0.0)
        value_edit = QLineEdit(str(current_val))
        value_edit.setFixedWidth(100)
        value_edit.setToolTip("Value or expression (e.g., 3.14 or rand(0, 10))")

        # Result label to show evaluated value
        result_label = QLabel(f"→ {current_val:.4g}")
        result_label.setFixedWidth(70)
        result_label.setStyleSheet("color: gray;")

        def on_value_change():
            text = value_edit.text().strip()
            try:
                val = self._eval_variable_expr(text)
                self._set_particle_variable(p.uid, var_name, val)
                result_label.setText(f"→ {val:.4g}")
            except Exception:
                result_label.setText("→ ?")

        value_edit.editingFinished.connect(on_value_change)
        layout.addWidget(value_edit)
        layout.addWidget(result_label)

        # Delete button
        del_btn = QToolButton()
        del_btn.setText("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setToolTip("Delete this variable from all particles")
        del_btn.clicked.connect(lambda: self._delete_particle_variable(var_name))
        layout.addWidget(del_btn)

        layout.addStretch()
        return row

    def _eval_variable_expr(self, expr: str) -> float:
        """Evaluate a variable expression, supporting rand(a, b) for random floats."""
        expr = expr.strip()

        # Check for rand(a, b) pattern
        import re
        rand_match = re.match(r'^rand\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)$', expr, re.IGNORECASE)
        if rand_match:
            a = float(rand_match.group(1))
            b = float(rand_match.group(2))
            return random.uniform(a, b)

        # Otherwise try to parse as a float
        return float(expr)

    def _add_particle_variable(self):
        """Add a new custom variable to all particles."""
        existing_names = set()
        for p in self.canvas.particles:
            existing_names.update(p.custom_vars.keys())

        idx = 1
        while f'v{idx}' in existing_names:
            idx += 1
        var_name = f'v{idx}'

        for p in self.canvas.particles:
            p.custom_vars[var_name] = 0.0

        self.sync_side_list(preserve_selection=False)

    def _rename_particle_variable(self, old_name: str, new_name: str):
        """Rename a custom variable across all particles."""
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        for p in self.canvas.particles:
            if old_name in p.custom_vars:
                p.custom_vars[new_name] = p.custom_vars.pop(old_name)

        self.sync_side_list(preserve_selection=True)

    def _set_particle_variable(self, uid: str, var_name: str, value: float):
        """Set a custom variable value for a specific particle."""
        for p in self.canvas.particles:
            if p.uid == uid:
                p.custom_vars[var_name] = value
                break

    def _delete_particle_variable(self, var_name: str):
        """Delete a custom variable from all particles."""
        for p in self.canvas.particles:
            p.custom_vars.pop(var_name, None)
        self.sync_side_list(preserve_selection=True)

    def _hide_particle(self, uid: str):
        for p in self.canvas.particles:
            if p.uid == uid:
                p.hiden = not p.hiden
                break
        # Defer the sync to avoid destroying the button while it's being clicked
        QTimer.singleShot(0, lambda: self.sync_side_list(preserve_selection=True))
        self.canvas.update()


    def apply_axis_labels(self):
        self.canvas.set_axis_labels(
            self.x_label_input.text(),
            self.y_label_input.text(),
            self.x_unit_input.text(),
            self.y_unit_input.text(),
        )

    def save_to_file(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Save JSON', '', 'JSON files (*.json)')
        if not fname:
            return

        # Gather definitions from def_rows
        defs = []
        for row in self.def_rows:
            defs.append({
                'kind': (row['kind'].text() or '').strip(),
                'name': (row['name'].text() or '').strip(),
                'expr': (row['expr'].text() or '').strip(),
            })

        # Gather gate states
        gates_state = {}
        for name, g in self.gates.items():
            gates_state[name] = int(g.state)

        data = {
            'systems': [s.to_dict() for s in self.canvas.systems],
            'definitions': defs,
            'gates_state': gates_state,
            'particles': [
                {
                    'x': p.x, 'y': p.y,
                    'x0': p.x0, 'y0': p.y0,
                    'color': p.color.name(),
                    'name': p.name,
                    'system_id': p.system_id
                }
                for p in self.canvas.particles
            ],
            'time': self.canvas.t,
            'time_scale': self.canvas.time_scale,
            'scale': self.canvas.scale,
            'offset': self.canvas.offset.tolist(),
            'fade': self.fade_spin.value(),
            'x_label': self.x_label_input.text(),
            'y_label': self.y_label_input.text(),
            'x_unit': self.x_unit_input.text(),
            'y_unit': self.y_unit_input.text(),
        }
        with open(fname, 'w') as f:
            json.dump(data, f, indent=2)

    '''
    def load_from_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Open JSON', '', 'JSON files (*.json)')
        if not fname:
            return
        with open(fname, 'r') as f:
            data = json.load(f)

        # Clear existing definitions UI
        for row in list(self.def_rows):
            self.remove_definition_row(row)

        # Load definitions
        for d in data.get('definitions', []):
            self.add_definition_row(default_kind=(d.get('kind') or 'const'))
            row = self.def_rows[-1]
            row['kind'].setText(d.get('kind', 'const'))
            row['name'].setText(d.get('name', 'a'))
            row['expr'].setText(d.get('expr', '1.0'))

        # Rebuild model environment before loading systems (so equations compile correctly)
        self.rebuild_model_env_and_recompile()

        # Restore gate states if present
        gate_state = data.get('gates_state', {})
        for name, st in gate_state.items():
            g = self.gates.get(name)
            if g is not None:
                try:
                    g.state = 1 if int(st) else 0
                except Exception:
                    pass

        # Clear existing systems
        for uid in list(self.system_editors.keys()):
            editor = self.system_editors.pop(uid)
            editor.setParent(None)
            editor.deleteLater()
        self.canvas.systems.clear()
        self.canvas.particles.clear()
        self.canvas.x_overlay.system_traces.clear()
        self.canvas.y_overlay.system_traces.clear()

        # Load systems
        for sys_data in data.get('systems', []):
            system = DynamicalSystem.from_dict(sys_data)
            # Apply the model environment to the system before compiling
            system.model_env = self.model_env
            system.compile_equations()
            self.canvas.add_system(system)

            editor = SystemEditor(system)
            editor.on_change = self._on_system_changed
            editor.on_color_change = self._on_system_color_changed
            self.system_editors[system.uid] = editor
            self.systems_vlayout.addWidget(editor)

        self._update_system_combo()

        # Load particles
        for pi in data.get('particles', []):
            p = Particle(
                pi.get('x0', pi['x']),
                pi.get('y0', pi['y']),
                color=pi.get('color'),
                name=pi.get('name'),
                system_id=pi.get('system_id')
            )
            p.x = float(pi['x'])
            p.y = float(pi['y'])
            p.reset_history()
            p.max_history_time = data.get('fade', 5)
            self.canvas.particles.append(p)

        self.canvas.t = float(data.get('time', 0.0))
        self.canvas.time_scale = float(data.get('time_scale', 1.0))
        self.speed_spin.setValue(float(self.canvas.time_scale))

        self.canvas.scale = data.get('scale', self.canvas.scale)
        off = data.get('offset', self.canvas.offset.tolist())
        self.canvas.offset = np.array(off)

        self.fade_spin.setValue(int(data.get('fade', 5)))
        self.selected_particle_uid = None
        self.x_label_input.setText(data.get('x_label', 'x'))
        self.y_label_input.setText(data.get('y_label', 'y'))
        self.x_unit_input.setText(data.get('x_unit', ''))
        self.y_unit_input.setText(data.get('y_unit', ''))
        self.apply_axis_labels()
        self.sync_side_list(preserve_selection=False)
        self.canvas.update()
    '''

    def load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load', '', 'JSON (*.json)')
        if not path:
            return

        with open(path, 'r') as f:
            data = json.load(f)

        # Clear existing definitions UI
        for row in list(self.def_rows):
            self.remove_definition_row(row)

        # Load definitions
        for d in data.get('definitions', []):
            self.add_definition_row(default_kind=d.get('kind', 'const'))
            row = self.def_rows[-1]
            row['kind'].setText(d.get('kind', 'const'))
            row['name'].setText(d.get('name', ''))
            row['expr'].setText(d.get('expr', ''))

        # Rebuild model environment before loading systems
        self.rebuild_model_env_and_recompile()

        # Restore gate states if present
        gate_state = data.get('gates_state', {})
        for name, st in gate_state.items():
            if name in self.gates:
                self.gates[name].state = st

        # Clear existing systems and editors
        for ew in list(self.system_editors.values()):
            ew.setParent(None)
        self.system_editors.clear()
        self.canvas.systems.clear()
        self.canvas.particles.clear()
        self.canvas.x_overlay.clear()
        self.canvas.y_overlay.clear()

        # Load systems
        for sd in data.get('systems', []):
            system = DynamicalSystem.from_dict(sd)
            system.model_env = self.model_env
            system.compile_equations()
            self.canvas.systems.append(system)

            editor = SystemEditor(system)
            editor.on_change = self._on_system_changed
            editor.on_color_change = self._on_system_color_changed
            self.system_editors[system.uid] = editor
            self.systems_vlayout.addWidget(editor)

        # Load particles and register traces
        for pd in data.get('particles', []):
            p = Particle(
                x0=pd['x0'],
                y0=pd['y0'],
                color=pd.get('color'),
                name=pd.get('name'),
                system_id=pd.get('system_id')
            )
            p.uid = pd.get('uid', p.uid)
            p.hiden = pd.get('hiden', False)
            self.canvas.particles.append(p)

            # Register particle trace in overlays
            system = self.canvas.get_system(p.system_id)
            if system:
                self.canvas.x_overlay.add_system(p.uid, system.color, system.name)
                self.canvas.y_overlay.add_system(p.uid, system.color, system.name)

        self._update_system_combo()

        # Restore other state
        self.canvas.t = float(data.get('time', 0.0))
        self.canvas.time_scale = float(data.get('time_scale', 1.0))
        self.speed_spin.setValue(float(self.canvas.time_scale))
        self.canvas.scale = data.get('scale', self.canvas.scale)
        off = data.get('offset', self.canvas.offset.tolist())
        self.canvas.offset = np.array(off)
        self.fade_spin.setValue(int(data.get('fade', 5)))

        self.x_label_input.setText(data.get('x_label', 'x'))
        self.y_label_input.setText(data.get('y_label', 'y'))
        self.x_unit_input.setText(data.get('x_unit', ''))
        self.y_unit_input.setText(data.get('y_unit', ''))
        self.apply_axis_labels()

        self.selected_particle_uid = None
        self.sync_side_list(preserve_selection=False)
        self.canvas.field_cache = {}
        self.canvas.update()

        # Set active system to the first loaded system
        if self.canvas.systems:
            self.canvas.active_system_uid = self.canvas.systems[0].uid

    def _rename_particle_variable(self, old_name: str, new_name: str):
        """Rename a custom variable across all particles."""
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        # Check if name is valid and not already in use
        if not new_name.isidentifier():
            return
        if new_name in ('x', 'y', 't', 'dt'):
            return

        for p in self.canvas.particles:
            if old_name in p.custom_vars:
                val = p.custom_vars.pop(old_name)
                p.custom_vars[new_name] = val

        self.sync_side_list(preserve_selection=True)


    def _set_particle_variable(self, uid: str, var_name: str, value: float):
        """Set a custom variable value for a specific particle."""
        for p in self.canvas.particles:
            if p.uid == uid:
                p.custom_vars[var_name] = float(value)
                break


    def _delete_particle_variable(self, var_name: str):
        """Delete a custom variable from all particles."""
        for p in self.canvas.particles:
            p.custom_vars.pop(var_name, None)
        self.sync_side_list(preserve_selection=True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Phase Portrait Simulator')
        self.resize(1200, 800)

        # --- Central layout: a compact header row (File + tabs) + the tab pages below ---
        central = QWidget()
        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central.setLayout(central_layout)
        self.setCentralWidget(central)
        # Real tab widget (holds pages), but we hide its built-in tab bar.
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()

        # External tab bar shown in the header.
        self.header_tabbar = QTabBar()
        self.header_tabbar.setExpanding(False)
        self.header_tabbar.setMovable(True)
        self.header_tabbar.setTabsClosable(True)
        self.header_tabbar.tabCloseRequested.connect(self.close_tab)
        self.header_tabbar.currentChanged.connect(self.tabs.setCurrentIndex)

        self.tabs.currentChanged.connect(self.header_tabbar.setCurrentIndex)

        # Handle reordering in the header tabbar
        self.header_tabbar.tabMoved.connect(self.on_tab_moved)

        # “File” menu button
        self.file_menu = QMenu('File', self)
        self.file_button = QToolButton()
        self.file_button.setText('File')
        self.file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.file_button.setMenu(self.file_menu)

        new_action = QAction('New Tab', self)
        new_action.triggered.connect(self.add_tab)
        self.file_menu.addAction(new_action)

        save_action = QAction('Save Tab', self)
        save_action.triggered.connect(self.save_tab)
        self.file_menu.addAction(save_action)

        load_action = QAction('Load Tab', self)
        load_action.triggered.connect(self.load_tab)
        self.file_menu.addAction(load_action)

        # Header row widget
        header = QWidget()
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(8)
        header.setLayout(header_layout)

        header_layout.addWidget(self.file_button)
        header_layout.addWidget(self.header_tabbar, 1)

        # Keep header height compact (optional styling)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        central_layout.addWidget(header)
        central_layout.addWidget(self.tabs, 1)

        self.add_tab()


    def _sync_header_tab_text(self, idx: int):
        if idx < 0 or idx >= self.tabs.count():
            return
        self.header_tabbar.setTabText(idx, self.tabs.tabText(idx))

    def add_tab(self):
        t = PhaseTab()
        title = f'Tab {self.tabs.count() + 1}'

        idx = self.tabs.addTab(t, title)
        self.header_tabbar.addTab(title)

        self.tabs.setCurrentIndex(idx)
        self.header_tabbar.setCurrentIndex(idx)

    def close_tab(self, index: int):
        if index < 0 or index >= self.tabs.count():
            return
        # Keep at least one tab
        if self.tabs.count() <= 1:
            return

        w = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.header_tabbar.removeTab(index)
        if w is not None:
            w.deleteLater()

        # Ensure indices remain aligned
        cur = min(index, self.tabs.count() - 1)
        self.tabs.setCurrentIndex(cur)
        self.header_tabbar.setCurrentIndex(cur)

    def on_tab_moved(self, from_idx: int, to_idx: int):
        # Mirror the move in the real QTabWidget so pages stay aligned with header tabs
        if from_idx == to_idx:
            return
        w = self.tabs.widget(from_idx)
        text = self.tabs.tabText(from_idx)

        self.tabs.removeTab(from_idx)
        self.tabs.insertTab(to_idx, w, text)
        self.tabs.setCurrentIndex(to_idx)

    def save_tab(self):
        cur = self.tabs.currentWidget()
        if isinstance(cur, PhaseTab):
            cur.save_to_file()

    def load_tab(self):
        cur = self.tabs.currentWidget()
        if isinstance(cur, PhaseTab):
            cur.load_from_file()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())