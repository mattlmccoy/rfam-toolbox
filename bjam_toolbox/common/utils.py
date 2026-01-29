"""Utility functions for BJAM Image Analysis Tool."""
import math

def distance(point1, point2):
    """Compute Euclidean distance between two points."""
    return math.hypot(point2[0] - point1[0], point2[1] - point1[1])

def centroid_from_contour(contour):
    """Compute centroid (x, y) from contour points."""
    # TODO: implement using moments
    pass
