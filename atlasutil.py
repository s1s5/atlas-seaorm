import datetime
import glob
import os
import random
import re
import select
import shutil
import subprocess
import tempfile
import time
import uuid
from subprocess import run


def get_previous_schema(td: str, down_dir: str):
    if os.path.exists(down_dir):
        return sorted(glob.glob(os.path.join(down_dir, "schema-*")), reverse=True)[0]
    previous_schema = os.path.join(td, uuid.uuid4().hex + ".sql")
    with open(previous_schema, "w"):
        pass
    return previous_schema


def get_latest_migration_file(dir: str):
    return sorted(glob.glob(os.path.join(dir, "*.sql")), reverse=True)[0]


def copy_schema(to: str, name: str, down_dir: str):
    if os.path.isfile(to):
        shutil.copy(to, os.path.join(down_dir, f"schema-{name}"))
    else:
        shutil.copytree(to, os.path.join(down_dir, f"schema-{name}"))


def make_migration(dir: str, name: str, to: str):
    td = tempfile.mkdtemp()
    up_dir = os.path.join(dir, "up")
    down_dir = os.path.join(dir, "down")

    previous_schema = get_previous_schema(td=td, down_dir=down_dir)

    try:
        prev_migration_file = get_latest_migration_file(up_dir)
    except IndexError:
        prev_migration_file = None

    run(
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
        check=True,
    )
    up_migration_file = get_latest_migration_file(up_dir)
    if prev_migration_file == up_migration_file:
        return

    try:
        temp_up_dir = os.path.join(td, "up")
        shutil.copytree(up_dir, temp_up_dir)
        run(
            [
                "atlas",
                "migrate",
                "diff",
                name,
                "--to",
                f"file://{previous_schema}",
                "--dev-url",
                "docker://postgres/15/dev?search_path=public",
                "--format",
                '{{ sql . "  " }}',
                "--dir",
                f"file://{temp_up_dir}",
            ],
            check=True,
        )
        down_migration_file = get_latest_migration_file(temp_up_dir)
        os.makedirs(down_dir, exist_ok=True)
        shutil.copy(
            down_migration_file,
            os.path.join(down_dir, os.path.basename(up_migration_file)),
        )

        copy_schema(
            to=to,
            name=os.path.basename(up_migration_file),
            down_dir=down_dir,
        )
    except Exception:
        os.remove(up_migration_file)

        filename = os.path.join(down_dir, os.path.basename(up_migration_file))
        if os.path.exists(filename):
            os.remove(filename)
        raise
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
    t = os.path.splitext(basename)[0]
    mod_name = "m" + t[:8] + "_" + t[8:]  # seaormのスタイルに合わせる
    up_fn = os.path.relpath(os.path.join(dir, "up", basename), src_dir)
    down_fn = os.path.relpath(os.path.join(dir, "down", basename), src_dir)
    up_cmd = EXEC_SQL % up_fn
    down_cmd = EXEC_SQL % down_fn

    with open(os.path.join(src_dir, mod_name + ".rs"), "w") as fp:
        fp.write(MIGRATION_FILE_TEMPLATE % ("", up_cmd, down_cmd))

    return mod_name


def update_seaorm_lib(src_dir: str, mod_name: str):
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
    generate_entity(to=schema, src_dir=src_dir, mod_name=mod_name)
    with open(os.path.join(src_dir, mod_name, "mod.rs"), "w") as fp:
        fp.write(MIGRATION_FILE_TEMPLATE % ("mod entity;", "", ""))

    update_seaorm_lib(src_dir=src_dir, mod_name=mod_name)


def run_postgres(port: int):
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
        return p
    except Exception:
        p.kill()
        raise


def generate_entity(to: str, src_dir: str, mod_name: str):
    port = random.randint(10000, 65536)
    p = run_postgres(port)
    try:
        postgres_url = f"postgres://postgres:pass@localhost:{port}/postgres"
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
        run(
            [
                "sea-orm-cli",
                "generate",
                "entity",
                "-u",
                postgres_url,
                "-o",
                os.path.join(src_dir, mod_name, "entity"),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        p.terminate()


def __entry_point():
    import argparse

    parser = argparse.ArgumentParser(
        description="create migration files",  # プログラムの説明
    )
    subparsers = parser.add_subparsers()

    parser_schema = subparsers.add_parser("schema", help="see `schema -h`")
    parser_schema.add_argument("--name", default="schema")
    parser_schema.add_argument("--to", default="migration/schema")
    parser_schema.add_argument("--dir", default="migration/atlas")
    parser_schema.add_argument("--src-dir", default="migration/src")
    parser_schema.set_defaults(
        handler=lambda args: create_schema_migration(**dict(args._get_kwargs()))
    )

    parser_data = subparsers.add_parser("data", help="see `data -h`")
    parser_data.add_argument("--name", default="data")
    parser_data.add_argument("--dir", default="migration/atlas")
    parser_data.add_argument("--src-dir", default="migration/src")
    parser_data.set_defaults(
        handler=lambda args: create_data_migration(**dict(args._get_kwargs()))
    )

    args = parser.parse_args()
    if hasattr(args, "handler"):
        args.handler(args)
    else:
        # 未知のサブコマンドの場合はヘルプを表示
        parser.print_help()


if __name__ == "__main__":
    __entry_point()
