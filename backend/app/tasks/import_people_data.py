from __future__ import annotations

import argparse

from app.db.session import SessionLocal, init_db
from app.services.importer import ImportService


def main() -> None:
    parser = argparse.ArgumentParser(description='Import people_dataset_v1.json into the backend database.')
    parser.add_argument('--force-rebuild', action='store_true', help='Clear existing tables before import.')
    args = parser.parse_args()

    init_db()
    with SessionLocal() as db:
        summary = ImportService(db).import_dataset(force_rebuild=args.force_rebuild)
    print(summary)


if __name__ == '__main__':
    main()
