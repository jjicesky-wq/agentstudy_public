import os
from collections.abc import Iterable
from typing import Any, Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from env_vars import (
    PG_DBNAME,
    PG_HOST,
    PG_PASSWORD,
    PG_PORT,
    PG_SU_PASSWORD,
    PG_SU_USERNAME,
    PG_USERNAME,
    SQLITE_FILE_DIRECTORY,
)

# test local db
sqlite_local_db_filename = "sql_app.db"

# prod db
pg_url = f"postgresql://{PG_USERNAME}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}"

# Set up the database connection based on environment variables
DB_URL = pg_url
if PG_PASSWORD is not None and PG_HOST is not None:
    engine = create_engine(pg_url)
    DB_URL = pg_url
else:
    # Make sure the dir exists
    os.makedirs(SQLITE_FILE_DIRECTORY, exist_ok=True)
    # test local db
    DB_URL = f"sqlite:///{SQLITE_FILE_DIRECTORY}/{sqlite_local_db_filename}"
    # test db connection
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Utilities for get db session and clone db model
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def clone_model(
    obj: Any, omit_pk: bool = True, omit: Optional[Iterable[str]] = None
) -> Any:
    """
    Create a deep copy of the model.

    - omit_pk: skip primary-key columns
    - omit: iterable of column names to skip
    """
    cls = type(obj)
    data = {}
    for c in cls.__table__.columns:
        if omit_pk and c.primary_key:
            continue
        if omit and c.name in omit:
            continue
        data[c.name] = getattr(obj, c.name)
    return cls(**data)


def clone_model_into(
    dst: Any,
    src: Any,
    omit_pk: bool = True,
    omit: Optional[Iterable[str]] = None,
    skip_none: bool = False,
):
    """
    Copy all column fields from `src` to `dst` (in-place).

    - omit_pk: skip primary-key columns
    - omit: iterable of column names to skip
    - skip_none: if True, do not overwrite with None values
    """
    omit = set(omit or [])

    src_mapper = sa_inspect(type(src))
    dst_mapper = sa_inspect(type(dst))

    # Columns to copy = intersection (safe if classes differ)
    src_cols = {c.key: c for c in src_mapper.columns}
    dst_cols = {c.key: c for c in dst_mapper.columns}

    keys = src_cols.keys() & dst_cols.keys()

    for key in keys:
        col = dst_cols[key]
        if omit_pk and col.primary_key:
            continue
        if key in omit:
            continue

        value = getattr(src, key)
        if skip_none and value is None:
            continue

        setattr(dst, key, value)

    return dst


# Utilities for creating the user and tables
def create_user_and_db(
    superuser: str,
    superuser_password: str,
    host: str,
    port: str,
    user: str,
    password: str,
    dbname: str,
):
    cursor = None
    connection = None
    try:
        connection = psycopg2.connect(
            dbname="postgres",
            user=superuser,
            password=superuser_password,
            host=host,
            port=port,
        )
        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = connection.cursor()

        user_exist = False
        try:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", (user,))
            if cursor.fetchone() is not None:
                user_exist = True
        except:
            user_exist = False

        database_exist = False
        try:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (dbname,))
            if cursor.fetchone() is not None:
                database_exist = True
        except:
            database_exist = False

        # Create the new database
        if not database_exist:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            print(f"Database '{dbname}' created successfully.")
        else:
            print(f"Database '{dbname}' already exists")

        # Create the new user with the specified password
        if not user_exist:
            cursor.execute(
                sql.SQL("CREATE USER {} WITH ENCRYPTED PASSWORD %s").format(
                    sql.Identifier(user)
                ),
                [password],
            )
            print(f"User '{user}' created successfully.")
        else:
            print(f"User '{user}' already exists")

        # Grant all privileges on the new database to the new user
        cursor.execute(
            sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
                sql.Identifier(dbname), sql.Identifier(user)
            )
        )

        cursor.execute(
            sql.SQL("GRANT ALL ON DATABASE {} TO {}").format(
                sql.Identifier(dbname), sql.Identifier(user)
            )
        )

        cursor.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(dbname), sql.Identifier(user)
            )
        )

        print(f"Granted all privileges on database '{dbname}' to user '{user}'.")

    except Exception as error:
        print(f"Error: {error}")

    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def setup_database():
    # Drop all tables if they exist
    Base.metadata.drop_all(bind=engine)

    # Create tables
    Base.metadata.create_all(bind=engine)
    print("Created database tables")


if __name__ == "__main__":
    if PG_SU_USERNAME and PG_SU_PASSWORD:
        create_user_and_db(
            superuser=PG_SU_USERNAME,
            superuser_password=PG_SU_PASSWORD,
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USERNAME,
            password=PG_PASSWORD,
            dbname=PG_DBNAME,
        )
