"""
API Routes Package for Smart Study Planner AI
"""
try:
    from backend.routes.subjects_bp import subjects_bp
    from backend.routes.preferences_bp import preferences_bp
except ImportError:
    from routes.subjects_bp import subjects_bp
    from routes.preferences_bp import preferences_bp

__all__ = ["subjects_bp", "preferences_bp"]
