//! SeaORM Entity. Generated by sea-orm-codegen 0.10.1

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, DeriveEntityModel, Eq)]
#[sea_orm(table_name = "test_manager")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i64,
    pub name: String,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {
    #[sea_orm(has_many = "super::test_user::Entity")]
    TestUser,
}

impl Related<super::test_user::Entity> for Entity {
    fn to() -> RelationDef {
        Relation::TestUser.def()
    }
}

impl ActiveModelBehavior for ActiveModel {}
