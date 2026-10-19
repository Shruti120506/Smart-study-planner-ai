"""
Database package for Smart Study Planner AI
"""
from backend.database.db import get_db_connection, close_db_connection, init_db

__all__ = ["get_db_connection", "close_db_connection", "init_db"]
