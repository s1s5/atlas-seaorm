use super::m20231129_090123_set_manager_id_entity as entity;
use sea_orm::{ActiveModelTrait, EntityTrait, Set};
use sea_orm_migration::prelude::*;

#[derive(DeriveMigrationName)]
pub struct Migration;

#[async_trait::async_trait]
impl MigrationTrait for Migration {
    async fn up(&self, manager: &SchemaManager) -> Result<(), DbErr> {
        let db = manager.get_connection();

        let manager = entity::test_manager::Entity::find().one(db).await?.unwrap();

        for u in entity::test_user::Entity::find().all(db).await? {
            let mut m: entity::test_user::ActiveModel = u.try_into().unwrap();
            m.manager_id = Set(Some(manager.id));
            m.update(db).await?;
        }

        Ok(())
    }

    async fn down(&self, _manager: &SchemaManager) -> Result<(), DbErr> {
        Ok(())
    }
}
