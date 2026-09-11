"""Compatibility entry point. Always use the configured database path."""
from app import create_app
if __name__ == '__main__':
    create_app().cli.main(args=['migrate'], prog_name='migrate_db.py')
