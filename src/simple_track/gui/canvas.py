"""The layout canvas: draws the track and handles placing, dragging,
rotating and deleting pieces.

Model coordinates are millimetres with y up; the scene is millimetres with y
down (Qt's way), so every point is flipped on its way in and out.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from simple_track.core.geometry import Point, Pose, Transform, offset_polyline
from simple_track.core.layout import ImportedPiece, Layout, Piece, PlacedPiece

BOARD = QColor("#e9efe4")
GRID_MINOR = QColor("#dde5d6")
GRID_MAJOR = QColor("#c7d3be")
SLEEPER = QColor("#8a7a68")
SLEEPER_IMPORTED = QColor("#9a8f84")
SLEEPER_SELECTED = QColor("#3d7fd9")
RAIL = QColor("#2e3236")
FREE_END = QColor("#d64545")
ACTIVE_END = QColor("#f08c1a")

SNAP_PIXELS = 18  # how close (on screen) a dragged piece's end must come to snap
CONNECTOR_PICK_PIXELS = 10
ROTATE_STEP_DEGREES = 15.0


def to_scene(point: Point) -> QPointF:
    return QPointF(point[0], -point[1])


def from_scene(point: QPointF) -> Point:
    return (point.x(), -point.y())


class TrackItem(QGraphicsItem):
    """One piece of track: sleepers as a wide band, then the two rails."""

    def __init__(self, piece: Piece):
        super().__init__()
        self.piece = piece
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.rebuild()

    def rebuild(self) -> None:
        self.prepareGeometryChange()
        self._lines = [[to_scene(p) for p in line] for line in self.piece.polylines() if len(line) >= 2]
        half_gauge = self.piece.gauge_mm / 2.0
        self._rails = []
        for line in self.piece.polylines():
            if len(line) >= 2:
                for side in (half_gauge, -half_gauge):
                    self._rails.append([to_scene(p) for p in offset_polyline(line, side)])
        self._centre = QPainterPath()
        for line in self._lines:
            self._centre.moveTo(line[0])
            for p in line[1:]:
                self._centre.lineTo(p)
        stroker = QPainterPathStroker()
        stroker.setWidth(self.piece.sleeper_mm)
        stroker.setCapStyle(Qt.FlatCap)
        self._shape = stroker.createStroke(self._centre)
        self._bounds = self._shape.boundingRect().adjusted(-2, -2, 2, 2)

    def boundingRect(self) -> QRectF:
        return self._bounds

    def shape(self) -> QPainterPath:
        return self._shape

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self.isSelected():
            colour = SLEEPER_SELECTED
        elif isinstance(self.piece, ImportedPiece):
            colour = SLEEPER_IMPORTED
        else:
            colour = SLEEPER
        band = QPen(colour, self.piece.sleeper_mm, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin)
        painter.setPen(band)
        painter.drawPath(self._centre)
        rail = QPen(RAIL, max(0.6, self.piece.gauge_mm * 0.08), Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin)
        painter.setPen(rail)
        for line in self._rails:
            painter.drawPolyline(line)


class ConnectorLayer(QGraphicsItem):
    """Marks the ends of the track with nothing joined to them, and the
    active end where the next piece will go."""

    def __init__(self):
        super().__init__()
        self.setZValue(10)
        self.free: list[Pose] = []
        self.active: Pose | None = None
        self._bounds = QRectF()

    def set_connectors(self, free: list[Pose], active: Pose | None) -> None:
        self.prepareGeometryChange()
        self.free, self.active = free, active
        points = [to_scene((p.x, p.y)) for p in free]
        if points:
            xs, ys = [p.x() for p in points], [p.y() for p in points]
            self._bounds = QRectF(min(xs) - 60, min(ys) - 60, max(xs) - min(xs) + 120, max(ys) - min(ys) + 120)
        else:
            self._bounds = QRectF()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        scale = painter.worldTransform().m11() or 1.0
        radius = 4.0 / scale  # a constant size on screen
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(FREE_END))
        for pose in self.free:
            painter.drawEllipse(to_scene((pose.x, pose.y)), radius, radius)
        if self.active is not None:
            centre = to_scene((self.active.x, self.active.y))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(ACTIVE_END, 2.5 / scale))
            painter.drawEllipse(centre, radius * 2.2, radius * 2.2)
            h = math.radians(self.active.heading)
            tip = to_scene((self.active.x + math.cos(h) * 28 / scale, self.active.y + math.sin(h) * 28 / scale))
            painter.drawLine(centre, tip)


class LayoutCanvas(QGraphicsView):
    changed = Signal()  # the layout was edited
    cursor_moved = Signal(float, float)  # model mm
    selection_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.scene().setSceneRect(-100000, -100000, 200000, 200000)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setMouseTracking(True)
        self.scale(0.5, 0.5)

        self.layout_model = Layout()
        self._items: dict[str, TrackItem] = {}
        self._connectors = ConnectorLayer()
        self.scene().addItem(self._connectors)
        self.active: tuple[str, int] | None = None  # (piece id, connector index)
        self._last_placed: tuple[str, int, Pose] | None = None  # (piece id, local index, target)
        self._drag_from: Point | None = None
        self._dragged = False
        self._pan_from: QPointF | None = None
        self.scene().selectionChanged.connect(lambda: self.selection_changed.emit(len(self.selected_pieces())))

    # --- the model

    def set_layout(self, layout: Layout, fit: bool = True) -> None:
        self.layout_model = layout
        self.active = None
        self._last_placed = None
        self.refresh()
        if fit:
            self.zoom_to_fit()

    def refresh(self) -> None:
        selected = {p.id for p in self.selected_pieces()}
        for item in self._items.values():
            self.scene().removeItem(item)
        self._items = {}
        for piece in self.layout_model.pieces:
            item = TrackItem(piece)
            self.scene().addItem(item)
            item.setSelected(piece.id in selected)
            self._items[piece.id] = item
        self._update_connectors()

    def _update_connectors(self) -> None:
        free = self.layout_model.free_connectors()
        if self.active is not None and not any(p.id == self.active[0] and i == self.active[1] for p, i, _ in free):
            self.active = None
        if self.active is None and free:
            piece, index, _ = free[-1]
            self.active = (piece.id, index)
        self._connectors.set_connectors([pose for _, _, pose in free], self.active_pose())

    def active_pose(self) -> Pose | None:
        if self.active is None:
            return None
        piece = self.layout_model.get(self.active[0])
        if piece is None:
            return None
        connectors = piece.connectors()
        return connectors[self.active[1]] if self.active[1] < len(connectors) else None

    def selected_pieces(self) -> list[Piece]:
        return [item.piece for item in self.scene().selectedItems() if isinstance(item, TrackItem)]

    # --- editing

    def place(self, library_id: str, code: str, local_index: int = 0) -> PlacedPiece:
        """Put a library piece on the active end (or the middle of the view
        on an empty board) and make its far end the new active end."""
        target = self.active_pose()
        if target is None:
            centre = from_scene(self.mapToScene(self.viewport().rect().center()))
            target = Pose(centre[0], centre[1], 180.0)
        piece = self.layout_model.place(library_id, code, target, local_index)
        self._last_placed = (piece.id, local_index, target)
        connectors = piece.definition.connectors
        joined = local_index % len(connectors)
        onward = next((i for i in range(len(connectors)) if i != joined), None)
        self.active = (piece.id, onward) if onward is not None else None
        self.refresh()
        self.scene().clearSelection()
        self.changed.emit()
        return piece

    def next_end(self) -> bool:
        """Re-place the piece just added by its next connector — turns a
        point round, or a curve to bend the other way."""
        if self._last_placed is None:
            return False
        piece_id, local_index, target = self._last_placed
        piece = self.layout_model.get(piece_id)
        if not isinstance(piece, PlacedPiece) or piece.definition is None:
            return False
        count = len(piece.definition.connectors)
        local_index = (local_index + 1) % count
        local = piece.definition.connectors[local_index]
        piece.transform = Transform.aligning(local, target)
        self._last_placed = (piece_id, local_index, target)
        onward = next((i for i in range(count) if i != local_index), None)
        self.active = (piece_id, onward) if onward is not None else None
        self.refresh()
        self.changed.emit()
        return True

    def delete_selected(self) -> None:
        pieces = self.selected_pieces()
        if not pieces:
            return
        for piece in pieces:
            self.layout_model.remove(piece.id)
        self._last_placed = None
        self.refresh()
        self.changed.emit()

    def rotate_selected(self, degrees: float = ROTATE_STEP_DEGREES) -> None:
        pieces = self.selected_pieces()
        if not pieces:
            return
        xs, ys = [], []
        for piece in pieces:
            for line in piece.polylines():
                for x, y in line:
                    xs.append(x)
                    ys.append(y)
        centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        turn = Transform.rotation_about(centre, degrees)
        for piece in pieces:
            piece.moved(turn)
        self._last_placed = None
        self.refresh()
        self.changed.emit()

    def select_all(self) -> None:
        for item in self._items.values():
            item.setSelected(True)

    # --- view

    def zoom_to_fit(self) -> None:
        bounds = self.layout_model.bounds()
        if bounds is None:
            self.resetTransform()
            self.scale(0.5, 0.5)
            self.centerOn(0, 0)
            return
        x0, y0, x1, y1 = bounds
        rect = QRectF(QPointF(x0, -y1), QPointF(x1, -y0)).adjusted(-80, -80, 80, 80)
        self.fitInView(rect, Qt.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        current = self.transform().m11()
        if 0.01 <= current * factor <= 40:
            self.scale(factor, factor)

    def wheelEvent(self, event) -> None:
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, BOARD)
        scale = self.transform().m11()
        for step, colour in ((100.0, GRID_MINOR), (1000.0, GRID_MAJOR)):
            if step * scale < 8:
                continue
            painter.setPen(QPen(colour, 0))
            x = math.floor(rect.left() / step) * step
            while x < rect.right():
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                x += step
            y = math.floor(rect.top() / step) * step
            while y < rect.bottom():
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                y += step

    # --- mouse

    def _pick_connector(self, scene_pos: QPointF) -> tuple[str, int] | None:
        tolerance = CONNECTOR_PICK_PIXELS / (self.transform().m11() or 1.0)
        x, y = from_scene(scene_pos)
        best = None
        for piece, index, pose in self.layout_model.free_connectors():
            gap = math.hypot(pose.x - x, pose.y - y)
            if gap <= tolerance and (best is None or gap < best[0]):
                best = (gap, piece.id, index)
        return (best[1], best[2]) if best else None

    def mousePressEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_from = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            picked = self._pick_connector(scene_pos)
            if picked is not None:
                self.active = picked
                self._last_placed = None
                self._update_connectors()
                return
            item = self.itemAt(event.position().toPoint())
            if isinstance(item, TrackItem):
                if event.modifiers() & Qt.ControlModifier:
                    item.setSelected(not item.isSelected())
                    return
                if not item.isSelected():
                    self.scene().clearSelection()
                    item.setSelected(True)
                self._drag_from = from_scene(scene_pos)
                self._dragged = False
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        here = from_scene(scene_pos)
        self.cursor_moved.emit(here[0], here[1])
        if self._pan_from is not None:
            delta = event.position() - self._pan_from
            self._pan_from = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return
        if self._drag_from is not None:
            step = Transform(here[0] - self._drag_from[0], here[1] - self._drag_from[1], 0.0)
            self._drag_from = here
            for piece in self.selected_pieces():
                piece.moved(step)
                self._items[piece.id].rebuild()
            self._dragged = True
            self._update_connectors()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None:
            self._pan_from = None
            self.unsetCursor()
            return
        if self._drag_from is not None:
            self._drag_from = None
            if self._dragged:
                pieces = self.selected_pieces()
                snap = self.layout_model.snap_transform(pieces, SNAP_PIXELS / (self.transform().m11() or 1.0))
                if snap is not None:
                    for piece in pieces:
                        piece.moved(snap)
                self._last_placed = None
                self.refresh()
                self.changed.emit()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        elif key == Qt.Key_R:
            self.rotate_selected(-ROTATE_STEP_DEGREES if event.modifiers() & Qt.ShiftModifier else ROTATE_STEP_DEGREES)
        elif key == Qt.Key_Tab:
            self.next_end()
        elif key == Qt.Key_Escape:
            self.scene().clearSelection()
        else:
            super().keyPressEvent(event)

    def focusNextPrevChild(self, next: bool) -> bool:
        return False  # Tab belongs to "next end", not focus changes
