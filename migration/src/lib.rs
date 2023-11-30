pub use sea_orm_migration::prelude::*;

mod m20220101_000001_create_table;
mod m20231130_041058_create_user_table;
mod m20231130_041259_create_manager_table;
mod m20231130_041352_seed_data;
mod m20231130_041352_seed_data_entity;
mod m20231130_041439_add_foreign_key;
mod m20231130_041446_set_manager_id;
mod m20231130_041446_set_manager_id_entity;
mod m20231130_041529_set_nonnull;

pub struct Migrator;

#[async_trait::async_trait]
impl MigratorTrait for Migrator {
    fn migrations() -> Vec<Box<dyn MigrationTrait>> {
        vec![
            Box::new(m20220101_000001_create_table::Migration),
            Box::new(m20231130_041058_create_user_table::Migration),
            Box::new(m20231130_041259_create_manager_table::Migration),
            Box::new(m20231130_041352_seed_data::Migration),
            Box::new(m20231130_041439_add_foreign_key::Migration),
            Box::new(m20231130_041446_set_manager_id::Migration),
            Box::new(m20231130_041529_set_nonnull::Migration),
        ]
    }
}
