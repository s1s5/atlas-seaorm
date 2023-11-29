import glob
import os
import re
import shutil
import tempfile
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

MIGRATION_FILE_TEMPLATE = """
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


def generate_seaorm_migration(src_dir: str, dir: str, basename: str):
    mod_name = "m" + os.path.splitext(basename)[0]
    up_fn = os.path.relpath(os.path.join(dir, "up", basename), src_dir)
    down_fn = os.path.relpath(os.path.join(dir, "down", basename), src_dir)
    up_cmd = EXEC_SQL % up_fn
    down_cmd = EXEC_SQL % down_fn

    with open(os.path.join(src_dir, mod_name + ".rs"), "w") as fp:
        fp.write(MIGRATION_FILE_TEMPLATE % (up_cmd, down_cmd))

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
        fp.writelines(lines)


def main(dir: str, name: str, to: str):
    migration_filename = make_migration(dir=dir, name=name, to=to)
    if migration_filename is None:
        return
    mod_name = generate_seaorm_migration(
        src_dir="migration/src", dir=dir, basename=migration_filename
    )
    update_seaorm_lib(src_dir="migration/src", mod_name=mod_name)


def __entry_point():
    import argparse

    parser = argparse.ArgumentParser(
        description="",  # プログラムの説明
    )
    parser.add_argument("--name", default="diff")
    parser.add_argument("--to", default="migration/schema")
    parser.add_argument("--dir", default="migration/atlas")
    main(**dict(parser.parse_args()._get_kwargs()))


if __name__ == "__main__":
    __entry_point()
