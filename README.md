# use atlas migration files in sea-orm

- `python atlasutil.py schema  --name create_user_table --to ./test-schemas/00.sql`
- `python atlasutil.py schema  --name create_manager_table --to ./test-schemas/01.sql`
- `python atlasutil.py data  --name seed_data`
- `python atlasutil.py schema  --name add_foreign_key --to ./test-schemas/02.sql`
- `python atlasutil.py data  --name set_manager_id`
- `python atlasutil.py schema  --name set_nonnull --to ./test-schemas/03.sql`


# test
- `docker run --rm --network host -e POSTGRES_HOST_AUTH_METHOD=trust --mount type=tmpfs,destination=/var/lib/postgresql/data postgres:16`
- `export DATABASE_URL=postgres://postgres:password@localhost/postgres`
- `cargo run --bin migration`

# command reference
## 現在のデータベースの定義を確認する
- `atlas schema inspect -u "postgres://postgres:password@localhost/postgres?sslmode=disable"`
- `atlas schema inspect -u "postgres://postgres:password@localhost/postgres?sslmode=disable" --format "{{ sql . }}"`

## データベースと定義ファイルの差分を確認する
- `atlas schema diff --from "postgres://postgres:pass@localhost/postgres?sslmode=disable" --to file://../test-schemas/03.sql --dev-url "docker://postgres" --exclude "public.seaql_migrations"`
    
# reference
- https://atlasgo.io/atlas-schema/hcl-types#postgresql
- https://www.sea-ql.org/SeaORM/docs/generate-entity/entity-structure/
