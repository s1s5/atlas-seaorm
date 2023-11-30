import datetime
import glob
import logging
import os
import random
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import typing
import uuid
from subprocess import run

logger = logging.getLogger(__name__)


def setup_log(log_level: typing.Literal["debug", "info", "error"]):
    """loggerのセットアップ"""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s")
    )
    logger.addHandler(handler)

    logger.setLevel(
        {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "error": logging.ERROR,
        }[log_level.lower()]
    )


def get_previous_schema(td: str, up_dir: str):
    """前回のマイグレーション後のスキーマ"""
    if os.path.exists(up_dir):
        return up_dir
    previous_schema = os.path.join(td, uuid.uuid4().hex + ".sql")
    with open(previous_schema, "w"):
        pass
    return previous_schema


def get_latest_migration_file(dir: str):
    """最新のマイグレーションファイル"""
    return sorted(glob.glob(os.path.join(dir, "*.sql")), reverse=True)[0]


def copy_schema(to: str, name: str, down_dir: str):
    """down migrationを作成するために、スキーマをコピー"""
    if os.path.isfile(to):
        shutil.copy(to, os.path.join(down_dir, f"schema-{name}"))
    else:
        shutil.copytree(to, os.path.join(down_dir, f"schema-{name}"))


def make_migration(dir: str, name: str, to: str):
    """schemaマイグレーションのsqlファイル作成"""
    td = tempfile.mkdtemp()
    up_dir = os.path.join(dir, "up")
    down_dir = os.path.join(dir, "down")

    previous_schema = get_previous_schema(td=td, up_dir=up_dir)

    logger.info("creating down migration file")
    r = run(
        [
            "atlas",
            "schema",
            "diff",
            "--from",
            f"file://{to}",
            "--to",
            f"file://{previous_schema}",
            "--dev-url",
            "docker://postgres/15/dev?search_path=public",
            "--format",
            '{{ sql . "  " }}',
        ],
        capture_output=True,
    )
    if r.returncode != 0:
        logger.error("%s", r.stderr)
        raise Exception("process failed")
    down_migration_str = r.stdout.strip()

    if down_migration_str == "":
        logger.info("no migration created")
        return

    logger.info("creating up migration file")
    r = run(
        [
            "atlas",
            "migrate",
            "diff",
            name,
            "--to",
            f"file://{to}",
            "--dev-url",
            "docker://postgres/15/dev?search_path=public",
            "--format",
            '{{ sql . "  " }}',
            "--dir",
            f"file://{up_dir}",
        ],
        capture_output=True,
    )
    if r.returncode != 0:
        logger.error("%s", r.stderr)
        raise Exception("process failed")

    up_migration_file = get_latest_migration_file(up_dir)
    os.makedirs(down_dir, exist_ok=True)
    with open(os.path.join(down_dir, up_migration_file), "wb") as fp:
        fp.write(down_migration_str)

    logger.info("new migration file = %s", up_migration_file)

    return os.path.basename(up_migration_file)


EXEC_SQL = """
        manager
            .get_connection()
            .execute_unprepared(include_str!("%s"))
            .await?;
"""

MIGRATION_FILE_TEMPLATE = """%s
use sea_orm_migration::prelude::*;

#[derive(DeriveMigrationName)]
pub struct Migration;

#[async_trait::async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
%s
        Ok(())
    }

    async fn down(&self, manager: &SchemaManager) -> Result<(), DbErr> {
%s
        Ok(())
    }
}
"""


def generate_seaorm_migration(name: str, src_dir: str, dir: str, basename: str):
    """sea-ormのmigrationファイルの生成"""
    t = os.path.splitext(basename)[0]
    mod_name = "m" + t[:8] + "_" + t[8:]  # seaormのスタイルに合わせる
    logger.info("create seaorm migration file %s", mod_name)
    up_fn = os.path.relpath(os.path.join(dir, "up", basename), src_dir)
    down_fn = os.path.relpath(os.path.join(dir, "down", basename), src_dir)
    up_cmd = EXEC_SQL % up_fn
    down_cmd = EXEC_SQL % down_fn

    with open(os.path.join(src_dir, mod_name + ".rs"), "w") as fp:
        fp.write(MIGRATION_FILE_TEMPLATE % ("", up_cmd, down_cmd))

    return mod_name


def update_seaorm_lib(src_dir: str, mod_name: str):
    """lib.rsにmoduleを追加して、migrationsにも追加する"""
    logger.info("update %s/lib.rs for %s", src_dir, mod_name)

    with open(os.path.join(src_dir, "lib.rs"), "r") as fp:
        lines = fp.read().splitlines()

    xp = re.compile(r"mod\s+m[a-zA-Z0-9_]+;")
    line_index = [x[0] for x in enumerate(lines) if xp.match(x[1])][-1]
    lines.insert(line_index + 1, f"mod {mod_name};")

    xp = re.compile(r"\s+vec\!\[.*")
    line_indexes = [x[0] for x in enumerate(lines) if xp.match(x[1])]
    if len(line_indexes) != 1:
        raise Exception("Unsupported lib.rs")
    line_index = line_indexes[0]

    expr = f"Box::new({mod_name}::Migration)"
    if "]" in lines[line_index]:
        s = lines[line_index]
        ch_index = s.find("]")
        lines[line_index] = s[:ch_index] + f", {expr}" + s[ch_index:]
    else:
        end_index = [
            x[0] for x in enumerate(lines) if x[0] > line_index and "]" in x[1]
        ][0]
        lines.insert(end_index, (" " * 12) + expr + ",")

    with open(os.path.join(src_dir, "lib.rs"), "w") as fp:
        fp.write("\n".join(lines))

    run(["cargo", "fmt", "--", os.path.join(src_dir, "lib.rs")], check=True)


def add_mod_to_lib(src_dir: str, mod_name: str):
    """lib.rsにimportするmoduleを追加する"""
    logger.info("add %s to %s/lib.rs ", mod_name, src_dir)

    with open(os.path.join(src_dir, "lib.rs"), "r") as fp:
        lines = fp.read().splitlines()

    xp = re.compile(r"mod\s+m[a-zA-Z0-9_]+;")
    line_index = [x[0] for x in enumerate(lines) if xp.match(x[1])][-1]
    lines.insert(line_index + 1, f"mod {mod_name};")

    with open(os.path.join(src_dir, "lib.rs"), "w") as fp:
        fp.write("\n".join(lines))

    run(["cargo", "fmt", "--", os.path.join(src_dir, "lib.rs")], check=True)


def run_postgres(port: int):
    """postgresをdocker内で走らせる"""
    logger.info("running postgres in docker")
    p = subprocess.Popen(
        [
            "docker",
            "run",
            "--rm",
            "-p",
            f"{port}:5432",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "postgres:15",
        ],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        assert p.stderr
        poll_obj = select.poll()
        poll_obj.register(p.stderr, select.POLLIN)

        timeout = time.time() + 30
        for i in range(1000):
            poll_result = poll_obj.poll(max(1, timeout - time.time()))
            if poll_result:
                line = p.stderr.readline()
                if "database system is ready to accept connections" in str(line):
                    break
            if time.time() > timeout or i >= 999:
                raise Exception("timeout")
        logger.info("postgres started")
        return p
    except Exception:
        p.kill()
        raise


def generate_entity(to: str, ent_dir: str):
    """entityファイルを生成する"""
    port = random.randint(10000, 65536)
    p = run_postgres(port)
    try:
        postgres_url = f"postgres://postgres:pass@localhost:{port}/postgres"
        logger.info("applying schema %s", to)
        run(
            [
                "atlas",
                "schema",
                "apply",
                "--url",
                postgres_url + "?sslmode=disable",
                "--to",
                f"file://{to}",
                "--dev-url",
                "docker://postgres/15",
                "--auto-approve",
            ],
            check=True,
            capture_output=True,
        )
        logger.info("creating current entity to %s", ent_dir)
        run(
            [
                "sea-orm-cli",
                "generate",
                "entity",
                "-u",
                postgres_url,
                "-o",
                ent_dir,
            ],
            check=True,
            capture_output=True,
        )
    finally:
        p.terminate()


def create_schema_migration(
    dir: str, name: str, to: str, src_dir: str, **_other_kwargs
):
    migration_filename = make_migration(dir=dir, name=name, to=to)
    if migration_filename is None:
        return
    mod_name = generate_seaorm_migration(
        name=name, src_dir=src_dir, dir=dir, basename=migration_filename
    )
    update_seaorm_lib(src_dir=src_dir, mod_name=mod_name)


def create_data_migration(name: str, src_dir: str, dir: str, **_other_kwargs):
    now = datetime.datetime.utcnow()
    mod_name = now.strftime(f"m%Y%m%d_%H%M%S_{name}")

    schema = sorted(
        glob.glob(os.path.join(os.path.join(dir, "down"), "schema-*")), reverse=True
    )[0]
    generate_entity(to=schema, ent_dir=os.path.join(src_dir, f"{mod_name}_entity"))
    with open(os.path.join(src_dir, f"{mod_name}.rs"), "w") as fp:
        fp.write(
            MIGRATION_FILE_TEMPLATE
            % (f"use super::{mod_name}_entity as entity;", "", "")
        )

    update_seaorm_lib(src_dir=src_dir, mod_name=mod_name)
    add_mod_to_lib(src_dir=src_dir, mod_name=f"{mod_name}_entity")


def create_entity_files(dir: str, ent_dir: str, **_other_kwargs):
    migration_dir = os.path.join(dir, "up")
    generate_entity(to=migration_dir, ent_dir=ent_dir)


def __entry_point():
    import argparse

    parser = argparse.ArgumentParser(
        description="create migration files",  # プログラムの説明
    )
    parser.add_argument("--log-level", default="info")
    subparsers = parser.add_subparsers()

    parser_schema = subparsers.add_parser(
        "schema", help="create schema migration files"
    )
    parser_schema.add_argument("--name", default="schema")
    parser_schema.add_argument("--to", default="migration/schema")
    parser_schema.add_argument("--dir", default="migration/atlas")
    parser_schema.add_argument("--src-dir", default="migration/src")
    parser_schema.set_defaults(
        handler=lambda args: create_schema_migration(**dict(args._get_kwargs()))
    )

    parser_data = subparsers.add_parser("data", help="create data migration files")
    parser_data.add_argument("--name", default="data")
    parser_data.add_argument("--dir", default="migration/atlas")
    parser_data.add_argument("--src-dir", default="migration/src")
    parser_data.set_defaults(
        handler=lambda args: create_data_migration(**dict(args._get_kwargs()))
    )

    parser_data = subparsers.add_parser("entity", help="create entity files")
    parser_data.add_argument("--dir", default="migration/atlas")
    parser_data.add_argument("--ent-dir", default="src/entity")
    parser_data.set_defaults(
        handler=lambda args: create_entity_files(**dict(args._get_kwargs()))
    )

    args = parser.parse_args()
    setup_log(args.log_level)

    if hasattr(args, "handler"):
        args.handler(args)
    else:
        # 未知のサブコマンドの場合はヘルプを表示
        parser.print_help()


if __name__ == "__main__":
    __entry_point()
