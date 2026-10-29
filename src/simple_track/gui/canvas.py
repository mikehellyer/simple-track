"""The layout canvas: draws the track and handles placing, dragging,
rotating and deleting pieces.

Model coordinates are millimetres with y up; the scene is millimetres with y
down (Qt's way), so every point is flipped on its way in and out.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView

from simple_track.core.geometry import Point, Pose, Transform, offset_polyline
from simple_track.core.layout import ImportedPiece, Layout, Piece, PlacedPiece
from simple_track.core.library import find_piece
from simple_track.core.units import describe
from simple_track.gui.library_panel import decode_piece

BOARD = QColor("#e9efe4")
FLOOR = QColor("#d5d8d2")  # around the baseboard, once there is one
BASEBOARD = QColor("#efe5cf")
BASEBOARD_EDGE = QColor("#8f7650")
DIMENSION_TEXT = QColor("#5e4b2e")
GRID_MINOR = QColor("#dde5d6")
GRID_MAJOR = QColor("#c7d3be")
SLEEPER = QColor("#8a7a68")
SLEEPER_IMPORTED = QColor("#9a8f84")
SLEEPER_SELECTED = QColor("#3d7fd9")
RAIL = QColor("#2e3236")
FREE_END = QColor("#d64545")
ACTIVE_END = QColor("#f08c1a")
SNAP_TARGET = QColor("#2e9e4f")
GHOST_OPACITY = 0.55

SNAP_PIXELS = 18  # how close (on screen) a dragged piece's end must come to snap
DROP_SNAP_PIXELS = 30  # a piece dropped from the library reaches a little further
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
        self.snap_target: Pose | None = None  # where a dragged piece will join, if it's let go now
        self._bounds = QRectF()

    def set_snap_target(self, target: Pose | None) -> None:
        if target != self.snap_target:
            self.snap_target = target
            self.update()

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

    def shape(self) -> QPainterPath:
        # Only drawn, never clicked: an empty shape lets clicks through to
        # the track underneath (its bounds cover the whole layout).
        return QPainterPath()

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
        if self.snap_target is not None:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(SNAP_TARGET, 3.0 / scale))
            painter.drawEllipse(to_scene((self.snap_target.x, self.snap_target.y)), radius * 3, radius * 3)


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
        self.setAcceptDrops(True)
        self.scale(0.5, 0.5)

        self.layout_model = Layout()
        self._items: dict[str, TrackItem] = {}
        self._connectors = ConnectorLayer()
        self._connectors.setAcceptedMouseButtons(Qt.NoButton)
        self.scene().addItem(self._connectors)
        self.active: tuple[str, int] | None = None  # (piece id, connector index)
        self._last_placed: tuple[str, int, Pose] | None = None  # (piece id, local index, target)
        self._drag_from: Point | None = None
        self._dragged = False
        self._pan_from: QPointF | None = None
        self._press_at = QPointF()
        self._click_end: tuple[str, int] | None = None  # a free end pressed on, made active if it's just a click
        self._ghost: TrackItem | None = None  # the piece being dragged in from the library
        self.unit = "mm"  # for the baseboard's dimensions
        # A bound method, not a lambda: Qt drops it when the canvas goes, so a
        # selection change during teardown can't reach a deleted view.
        self.scene().selectionChanged.connect(self._on_scene_selection)

    def _on_scene_selection(self) -> None:
        self.selection_changed.emit(len(self.selected_pieces()))

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
        self.viewport().update()  # the baseboard is drawn behind the scene, not as an item

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

    def track_item_at(self, view_pos) -> "TrackItem | None":
        """The piece of track under a point of the view, if any."""
        for item in self.items(view_pos):
            if isinstance(item, TrackItem) and item is not self._ghost:
                return item
        return None

    def select_connected(self, piece: Piece) -> None:
        """Select the piece and everything joined to it."""
        joined = {p.id for p in self.layout_model.connected(piece)}
        for piece_id, item in self._items.items():
            item.setSelected(piece_id in joined)

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

    # --- dragging pieces in from the library

    def preview_piece(self, library_id: str, code: str, scene_pos: QPointF) -> Pose | None:
        """Show the piece being dragged in, centred on the mouse — or, near a
        free end, joined onto it. Returns the end it would join, if any."""
        definition = find_piece(library_id, code)
        if definition is None:
            self.clear_preview()
            return None
        x, y = from_scene(scene_pos)
        cx, cy = definition.centre()
        transform = Transform(x - cx, y - cy, 0.0)
        target = None
        reach = DROP_SNAP_PIXELS / (self.transform().m11() or 1.0)
        snap = self.layout_model.snap_placement(library_id, code, transform, reach)
        if snap is None:
            # Dropped right onto a free end: join the piece's first end there.
            near = min(((math.hypot(pose.x - x, pose.y - y), pose)
                        for _, _, pose in self.layout_model.free_connectors()), default=None, key=lambda t: t[0])
            if near is not None and near[0] <= reach:
                snap = (Transform.aligning(definition.connectors[0], near[1]), near[1])
        if snap is not None:
            transform, target = snap
        if self._ghost is None or not isinstance(self._ghost.piece, PlacedPiece) \
                or (self._ghost.piece.library_id, self._ghost.piece.code) != (library_id, code):
            self.clear_preview()
            self._ghost = TrackItem(PlacedPiece(library_id, code, transform))
            self._ghost.setOpacity(GHOST_OPACITY)
            self._ghost.setFlag(QGraphicsItem.ItemIsSelectable, False)
            self._ghost.setZValue(5)
            self.scene().addItem(self._ghost)
        else:
            self._ghost.piece.transform = transform
            self._ghost.rebuild()
        self._connectors.set_snap_target(target)
        return target

    def clear_preview(self) -> None:
        if self._ghost is not None:
            self.scene().removeItem(self._ghost)
            self._ghost = None
        self._connectors.set_snap_target(None)

    def drop_piece(self, library_id: str, code: str, scene_pos: QPointF) -> PlacedPiece | None:
        """Put the piece down where preview_piece() showed it."""
        self.preview_piece(library_id, code, scene_pos)
        if self._ghost is None:
            return None
        piece = PlacedPiece(library_id, code, self._ghost.piece.transform)
        self.clear_preview()
        self.layout_model.add(piece)
        self._last_placed = None
        free_here = [i for p, i, _ in self.layout_model.free_connectors() if p is piece]
        self.active = (piece.id, free_here[-1]) if free_here else None
        self.refresh()
        self.scene().clearSelection()
        self._items[piece.id].setSelected(True)
        self.changed.emit()
        self.setFocus()
        return piece

    def dragEnterEvent(self, event) -> None:
        if decode_piece(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        piece = decode_piece(event.mimeData())
        if piece is None:
            super().dragMoveEvent(event)
            return
        self.preview_piece(*piece, self.mapToScene(event.position().toPoint()))
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self.clear_preview()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        piece = decode_piece(event.mimeData())
        if piece is None:
            super().dropEvent(event)
            return
        self.drop_piece(*piece, self.mapToScene(event.position().toPoint()))
        event.acceptProposedAction()

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

    def baseboard_rect(self) -> QRectF | None:
        board = self.layout_model.baseboard
        if board is None:
            return None
        return QRectF(0.0, -board.depth_mm, board.width_mm, board.depth_mm)  # scene y runs down

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        board = self.baseboard_rect()
        if board is None:
            painter.fillRect(rect, BOARD)
        else:
            painter.fillRect(rect, FLOOR)
            painter.fillRect(board, BASEBOARD)
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

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        board = self.baseboard_rect()
        if board is None:
            return
        painter.setPen(QPen(BASEBOARD_EDGE, 2.0 / (self.transform().m11() or 1.0)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(board)
        # The dimensions, at a fixed size on screen: width under the board,
        # depth up its left side.
        layout = self.layout_model.baseboard
        bottom_left = self.mapFromScene(board.bottomLeft())
        bottom_right = self.mapFromScene(board.bottomRight())
        top_left = self.mapFromScene(board.topLeft())
        painter.save()
        painter.resetTransform()
        font = QFont(painter.font())
        font.setPointSizeF(9.5)
        painter.setFont(font)
        painter.setPen(DIMENSION_TEXT)
        width_text = describe(layout.width_mm, self.unit)
        depth_text = describe(layout.depth_mm, self.unit)
        painter.drawText(QRectF(bottom_left.x(), bottom_left.y() + 4, bottom_right.x() - bottom_left.x(), 18),
                         Qt.AlignHCenter | Qt.AlignTop, width_text)
        painter.translate(top_left.x() - 6, (top_left.y() + bottom_left.y()) / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-150, -18, 300, 18), Qt.AlignHCenter | Qt.AlignBottom, depth_text)
        painter.restore()

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
            item = self.track_item_at(event.position().toPoint())
            if picked is not None and item is None:
                self._make_active(picked)
                return
            if item is not None:
                if event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                    item.setSelected(not item.isSelected())
                    return
                if not item.isSelected():
                    self.scene().clearSelection()
                    item.setSelected(True)
                # Near a free end, a click (no drag) makes it the orange end;
                # pulling the mouse away moves the piece instead.
                self._click_end = picked
                self._press_at = event.position()
                self._drag_from = from_scene(scene_pos)
                self._dragged = False
                return
        super().mousePressEvent(event)

    def _make_active(self, end: tuple[str, int]) -> None:
        self.active = end
        self._last_placed = None
        self._update_connectors()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            item = self.track_item_at(event.position().toPoint())
            if item is not None:
                self.select_connected(item.piece)
                return
        super().mouseDoubleClickEvent(event)

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
            if not self._dragged and (event.position() - self._press_at).manhattanLength() \
                    < QApplication.startDragDistance():
                return  # a click with a shaky hand isn't a move
            step = Transform(here[0] - self._drag_from[0], here[1] - self._drag_from[1], 0.0)
            self._drag_from = here
            pieces = self.selected_pieces()
            for piece in pieces:
                piece.moved(step)
                self._items[piece.id].rebuild()
            self._dragged = True
            self._update_connectors()
            snap = self.layout_model.snap_candidate(pieces, SNAP_PIXELS / (self.transform().m11() or 1.0))
            self._connectors.set_snap_target(snap[1] if snap else None)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._pan_from is not None:
            self._pan_from = None
            self.unsetCursor()
            return
        if self._drag_from is not None:
            self._drag_from = None
            self._connectors.set_snap_target(None)
            if not self._dragged and self._click_end is not None:
                self._make_active(self._click_end)
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
