from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QMouseEvent, QPainterPath
from PyQt6.QtCore import Qt, QPoint, QPointF
from scipy.interpolate import splprep, splev
import numpy as np

class DrawingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.strokes = [] # Stores B-spline data ({'control_points', 'knots', 'degree', 'u'})
        self.current_stroke = [] # Stores raw points and pressure for the current stroke [(QPoint, pressure)]
        self.selected_control_point = None # (stroke_index, cp_index)
        self.setMouseTracking(True) # Enable tracking even when no button is pressed

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if a control point is being selected
            clicked_point = event.pos()
            clicked_point_f = QPointF(clicked_point) # Convert to QPointF
            for stroke_index, stroke_data in enumerate(self.strokes):
                control_points = stroke_data['control_points']
                for cp_index, cp in enumerate(control_points):
                    cp_qpointf = QPointF(cp[0], cp[1])
                    # Check if the click is close to the control point
                    if (clicked_point_f - cp_qpointf).manhattanLength() < 10: # Tolerance of 10 pixels
                        self.selected_control_point = (stroke_index, cp_index)
                        self.update()
                        return # Stop checking after finding a selected control point

            # If no control point is selected, start a new stroke
            pressure = event.pressure() if hasattr(event, 'pressure') else 1.0 # Get pressure safely
            self.current_stroke = [(event.pos(), pressure)] # Store point and pressure
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.selected_control_point is not None:
            # Move the selected control point
            stroke_index, cp_index = self.selected_control_point
            new_pos = event.pos()
            self.strokes[stroke_index]['control_points'][cp_index] = np.array([new_pos.x(), new_pos.y()])
            self.update() # Redraw the widget to show the updated spline

        elif event.buttons() == Qt.MouseButton.LeftButton:
            pressure = event.pressure() if hasattr(event, 'pressure') else 1.0 # Get pressure safely
            self.current_stroke.append((event.pos(), pressure)) # Store point and pressure
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.selected_control_point is not None:
                self.selected_control_point = None # Clear selected control point
                self.update()
            elif len(self.current_stroke) > 1:
                # Process the completed stroke if no control point was selected
                # Separate points and pressures
                points = [p for p, pressure in self.current_stroke]
                pressures = [pressure for p, pressure in self.current_stroke]

                # Remove consecutive duplicate points (based on position only)
                unique_points_with_pressure = [self.current_stroke[0]]
                for i in range(1, len(self.current_stroke)):
                    if self.current_stroke[i][0] != self.current_stroke[i-1][0]:
                        unique_points_with_pressure.append(self.current_stroke[i])

                if len(unique_points_with_pressure) > 2: # Need at least 3 unique points for quadratic spline
                    # Downsample points (take every 10th point)
                    downsampled_points_with_pressure = unique_points_with_pressure[::10] # Increased downsampling factor
                    if len(downsampled_points_with_pressure) < 3: # Ensure at least 3 points after downsampling
                         downsampled_points_with_pressure = unique_points_with_pressure # Use unique points if downsampling results in too few

                    points_only = np.array([(p.x(), p.y()) for p, pressure in downsampled_points_with_pressure])

                    # Use splprep to find the B-spline representation
                    try:
                        # Using degree 2 for quadratic splines
                        # Use a smoothing factor (s > 0) to get control points not on the curve
                        s_factor = len(points_only) # Starting with s = number of points, can be adjusted
                        tck, u = splprep(points_only.T, s=s_factor, k=2) # Changed degree to 2
                        # Store control points, knots, degree, and u
                        self.strokes.append({
                            'control_points': np.array(tck[1]).T,
                            'knots': tck[0],
                            'degree': tck[2],
                            'u': u,
                            'original_points_with_pressure': downsampled_points_with_pressure # Store downsampled points with pressure
                        })
                    except ValueError as e:
                        print(f"Could not create B-spline with {len(points_only)} points after preprocessing (degree 2): {e}")
                        pass # Do not add the stroke if spline creation fails
                else:
                     print(f"Not enough unique points ({len(unique_points_with_pressure)}) to create a B-spline (degree 2).")

                self.current_stroke = []
                self.update()
            else:
                self.current_stroke = [] # Clear stroke if not enough points
                self.update()


    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Default pen for B-splines
        pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        # Draw completed B-splines and control points
        for stroke_data in self.strokes:
            control_points = stroke_data['control_points']
            knots = stroke_data['knots']
            degree = stroke_data['degree']
            u = stroke_data['u']
            original_points_with_pressure = stroke_data.get('original_points_with_pressure', []) # Get original points with pressure

            # Reconstruct tck from stored components
            tck = (knots, control_points.T, degree)

            # Draw the B-spline curve (without pressure sensitivity for now)
            x_fine, y_fine = splev(np.linspace(0, u[-1], 100), tck)
            path = QPainterPath()
            path.moveTo(QPointF(x_fine[0], y_fine[0]))
            for i in range(1, len(x_fine)):
                path.lineTo(QPointF(x_fine[i], y_fine[i]))
            painter.drawPath(path)

            # Draw control points
            painter.save() # Save painter state
            painter.setPen(QPen(Qt.GlobalColor.red, 5, Qt.PenStyle.SolidLine))
            for cp in control_points:
                painter.drawPoint(QPointF(cp[0], cp[1]))
            painter.restore() # Restore painter state

        # Draw the current raw stroke with pressure sensitivity
        if len(self.current_stroke) > 1:
            painter.save() # Save painter state
            # Draw segments with varying thickness based on pressure
            for i in range(len(self.current_stroke) - 1):
                point1, pressure1 = self.current_stroke[i]
                point2, pressure2 = self.current_stroke[i+1]

                # Map pressure (0.0 to 1.0) to pen width (e.g., 1 to 10)
                pen_width = 1 + pressure1 * 9 # Vary from 1 to 10

                pen = QPen(Qt.GlobalColor.blue, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(point1, point2)
            painter.restore() # Restore painter state
