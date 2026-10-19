"""
Database package for Smart Study Planner AI
"""
try:
    from backend.database.db import get_db_connection, close_db_connection, init_db, load_sample_subjects
except ImportError:
    from database.db import get_db_connection, close_db_connection, init_db, load_sample_subjects

__all__ = ["get_db_connection", "close_db_connection", "init_db", "load_sample_subjects"]
