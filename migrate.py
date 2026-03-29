"""
Deprecated migration helper.

The project now uses PostgreSQL with automatic schema initialization in database.init_db().
This file is kept only to avoid confusion for old deployment scripts.
"""

if __name__ == "__main__":
    print("This project now initializes PostgreSQL schema automatically on startup.")
    print("No standalone SQLite migration script is used anymore.")
