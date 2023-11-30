use super::m20231130_041352_seed_data_entity as entity;
use sea_orm::*;
use sea_orm_migration::prelude::*;

#[derive(DeriveMigrationName)]
pub struct Migration;

#[async_trait::async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        let db = manager.get_connection();
        entity::test_user::ActiveModel {
            name: Set("u0".to_string()),
            ..Default::default()
        }
        .insert(db)
        .await?;

        entity::test_user::ActiveModel {
            name: Set("u1".to_string()),
            ..Default::default()
        }
        .insert(db)
        .await?;

        entity::test_user::ActiveModel {
            name: Set("u2".to_string()),
            ..Default::default()
        }
        .insert(db)
        .await?;

        entity::test_manager::ActiveModel {
            name: Set("m0".to_string()),
            ..Default::default()
        }
        .insert(db)
        .await?;
        Ok(())
    }

    async fn down(&self, _manager: &SchemaManager) -> Result<(), DbErr> {
        Ok(())
    }
}
