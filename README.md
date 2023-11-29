# 

``` diff
modified   migration/src/lib.rs
@@ -1,12 +1,16 @@
 pub use sea_orm_migration::prelude::*;
 
 mod m20220101_000001_create_table;
+mod m20231129_104301_add_field;
 
 pub struct Migrator;
 
 #[async_trait::async_trait]
 impl MigratorTrait for Migrator {
     fn migrations() -> Vec<Box<dyn MigrationTrait>> {
-        vec![Box::new(m20220101_000001_create_table::Migration)]
+        vec![
+            Box::new(m20220101_000001_create_table::Migration),
+            Box::new(m20231129_104301_add_field::Migration),
+        ]
     }
 }
```

``` rust
use sea_orm_migration::prelude::*;

#[derive(DeriveMigrationName)]
pub struct Migration;

#[async_trait::async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        // Replace the sample below with your own migration scripts
        todo!();

        manager
            .create_table(
                Table::create()
                    .table(Post::Table)
                    .if_not_exists()
                    .col(
                        ColumnDef::new(Post::Id)
                            .integer()
                            .not_null()
                            .auto_increment()
                            .primary_key(),
                    )
                    .col(ColumnDef::new(Post::Title).string().not_null())
                    .col(ColumnDef::new(Post::Text).string().not_null())
                    .to_owned(),
            )
            .await
    }

    async fn down(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        // Replace the sample below with your own migration scripts
        todo!();

        manager
            .drop_table(Table::drop().table(Post::Table).to_owned())
            .await
    }
}

/// Learn more at https://docs.rs/sea-query#iden
#[derive(Iden)]
enum Post {
    Table,
    Id,
    Title,
    Text,
}
```



python atlasutil.py schema  --name create_user_table --to ./test-schemas/00.sql
python atlasutil.py schema  --name create_manager_table --to ./test-schemas/01.sql
python atlasutil.py data  --name seed_data
python atlasutil.py schema  --name add_foreign_key --to ./test-schemas/02.sql
python atlasutil.py data  --name set_manager_id
python atlasutil.py schema  --name set_nonnull --to ./test-schemas/03.sql
